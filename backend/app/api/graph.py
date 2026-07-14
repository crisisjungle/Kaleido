"""
图谱相关API路由
采用项目上下文机制，服务端持久化状态
"""

import json
import os
import traceback
from flask import request, jsonify

from . import graph_bp
from ..config import Config
from ..services.ontology_generator import OntologyGenerator
from ..services.graph_builder import GraphBuilderService
from ..services.display_localization import public_error_message, sanitize_public_dto
from ..services.effort_contract import (
    EffortContractError,
    assert_effort_reference,
    build_effort_snapshot,
    normalize_effort_snapshot,
)
from ..services.map_seed_manager import MapSeedManager
from ..services.semantic_input import SemanticArtifactStore
from ..services.task_executor import TaskExecutor
from ..services.text_processor import TextProcessor
from ..utils.file_parser import FileParser
from ..utils.logger import get_logger
from ..models.task import TaskCancelledError, TaskManager, TaskStatus
from ..models.project import ProjectManager, ProjectStatus

# 获取日志器
logger = get_logger('envfish.api')


def _public_success(data, **metadata):
    payload = {"success": True, "data": sanitize_public_dto(data)}
    payload.update(metadata)
    return jsonify(payload)


def _public_failure(error, fallback: str, status: int = 500, *, code: str | None = None):
    payload = {
        "success": False,
        "error": public_error_message(error, fallback),
    }
    if code:
        payload["code"] = code
    return jsonify(payload), status


def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    if not filename or '.' not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    return ext in Config.ALLOWED_EXTENSIONS


# ============== 项目管理接口 ==============

@graph_bp.route('/project/<project_id>', methods=['GET'])
def get_project(project_id: str):
    """
    获取项目详情
    """
    project = ProjectManager.get_project(project_id)
    
    if not project:
        return jsonify({
            "success": False,
            "error": "项目不存在"
        }), 404
    
    payload = project.to_dict()
    semantic_artifact = SemanticArtifactStore.get_by_ref(project.semantic_artifact_ref)
    if semantic_artifact:
        payload["semantic_input"] = semantic_artifact.model_dump(mode="json")
    return _public_success(payload)


@graph_bp.route('/project/list', methods=['GET'])
def list_projects():
    """
    列出所有项目
    """
    limit = request.args.get('limit', 50, type=int)
    projects = ProjectManager.list_projects(limit=limit)
    
    return _public_success([p.to_dict() for p in projects], count=len(projects))


@graph_bp.route('/project/<project_id>', methods=['DELETE'])
def delete_project(project_id: str):
    """
    删除项目
    """
    success = ProjectManager.delete_project(project_id)
    
    if not success:
        return jsonify({
            "success": False,
            "error": "项目不存在或删除失败"
        }), 404
    
    return jsonify({
        "success": True,
        "message": "项目已删除"
    })


@graph_bp.route('/project/<project_id>/reset', methods=['POST'])
def reset_project(project_id: str):
    """
    重置项目状态（用于重新构建图谱）
    """
    project = ProjectManager.get_project(project_id)
    
    if not project:
        return jsonify({
            "success": False,
            "error": "项目不存在"
        }), 404
    
    # 重置到本体已生成状态
    if project.ontology:
        project.status = ProjectStatus.ONTOLOGY_GENERATED
    else:
        project.status = ProjectStatus.CREATED
    
    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    ProjectManager.save_project(project)
    
    return jsonify({
        "success": True,
        "message": "项目已重置",
        "data": sanitize_public_dto(project.to_dict())
    })


# ============== 接口1：上传文件并生成本体 ==============

@graph_bp.route('/ontology/generate', methods=['POST'])
def generate_ontology():
    """
    接口1：上传文件，分析生成本体定义
    
    请求方式：multipart/form-data
    
    参数：
        files: 上传的文件（PDF/MD/TXT），可多个
        simulation_requirement: 模拟需求描述（必填）
        project_name: 项目名称（可选）
        additional_context: 额外说明（可选）
        
    返回：
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "ontology": {
                    "entity_types": [...],
                    "edge_types": [...],
                    "analysis_summary": "..."
                },
                "files": [...],
                "total_text_length": 12345
            }
        }
    """
    try:
        logger.info("=== 开始生成本体定义 ===")
        
        # 获取参数
        simulation_requirement = request.form.get('simulation_requirement', '')
        project_name = request.form.get('project_name', '未命名项目')
        additional_context = request.form.get('additional_context', '')
        map_seed_id = str(request.form.get('map_seed_id') or '').strip()
        scene_id = str(request.form.get('scene_id') or '').strip()
        semantic_artifact_ref = {}
        if request.form.get('semantic_artifact_ref'):
            try:
                semantic_artifact_ref = json.loads(request.form.get('semantic_artifact_ref') or '{}')
            except (TypeError, ValueError, json.JSONDecodeError):
                semantic_artifact_ref = {}
        requested_effort_snapshot_id = str(request.form.get('effort_snapshot_id') or '').strip()
        requested_effort_level = str(request.form.get('effort_level') or 'high').strip()
        
        logger.debug(f"项目名称: {project_name}")
        logger.debug(f"模拟需求: {simulation_requirement[:100]}...")
        
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": "请提供模拟需求描述"
            }), 400
        
        # 获取上传的文件
        uploaded_files = request.files.getlist('files')
        if not uploaded_files or all(not f.filename for f in uploaded_files):
            return jsonify({
                "success": False,
                "error": "请至少上传一个文档文件"
            }), 400
        
        seed = MapSeedManager.get_seed(map_seed_id) if map_seed_id else None
        if map_seed_id and not seed:
            return jsonify({"success": False, "error": "地图种子不存在"}), 400
        if seed and seed.get("effort_snapshot"):
            effort_snapshot = normalize_effort_snapshot(seed.get("effort_snapshot"))
            if requested_effort_snapshot_id:
                assert_effort_reference(
                    effort_snapshot,
                    effort_snapshot_id=requested_effort_snapshot_id,
                    requested_level=requested_effort_level,
                )
        else:
            effort_snapshot = build_effort_snapshot(
                requested_effort_level,
                effort_snapshot_id=requested_effort_snapshot_id or None,
            )

        # 创建项目
        project = ProjectManager.create_project(name=project_name, effort_snapshot=effort_snapshot)
        project.simulation_requirement = simulation_requirement
        project.map_seed_id = map_seed_id or None
        project.scene_id = scene_id or None
        project.semantic_artifact_ref = (
            semantic_artifact_ref if isinstance(semantic_artifact_ref, dict) else {}
        )
        logger.info(f"创建项目: {project.project_id}")
        
        # 保存文件并提取文本
        document_texts = []
        all_text = ""
        
        for file in uploaded_files:
            if file and file.filename and allowed_file(file.filename):
                # 保存文件到项目目录
                file_info = ProjectManager.save_file_to_project(
                    project.project_id, 
                    file, 
                    file.filename
                )
                project.files.append({
                    "filename": file_info["original_filename"],
                    "size": file_info["size"]
                })
                
                # 提取文本
                text = FileParser.extract_text(file_info["path"])
                text = TextProcessor.preprocess_text(text)
                document_texts.append(text)
                all_text += f"\n\n=== {file_info['original_filename']} ===\n{text}"
        
        if not document_texts:
            ProjectManager.delete_project(project.project_id)
            return jsonify({
                "success": False,
                "error": "没有成功处理任何文档，请检查文件格式"
            }), 400
        
        # 保存提取的文本
        project.total_text_length = len(all_text)
        ProjectManager.save_extracted_text(project.project_id, all_text)
        logger.info(f"文本提取完成，共 {len(all_text)} 字符")
        
        # 生成本体
        logger.info("调用 LLM 生成本体定义...")
        generator = OntologyGenerator()
        ontology = generator.generate(
            document_texts=document_texts,
            simulation_requirement=simulation_requirement,
            additional_context=additional_context if additional_context else None
        )
        
        # 保存本体到项目
        entity_count = len(ontology.get("entity_types", []))
        edge_count = len(ontology.get("edge_types", []))
        logger.info(f"本体生成完成: {entity_count} 个实体类型, {edge_count} 个关系类型")
        
        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", [])
        }
        project.analysis_summary = ontology.get("analysis_summary", "")
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        ProjectManager.save_project(project)
        logger.info(f"=== 本体生成完成 === 项目ID: {project.project_id}")
        
        return _public_success({
                "project_id": project.project_id,
                "project_name": project.name,
                "ontology": project.ontology,
                "analysis_summary": project.analysis_summary,
                "files": project.files,
                "total_text_length": project.total_text_length,
                "effort_snapshot": project.effort_snapshot,
                "map_seed_id": project.map_seed_id,
        })
    except EffortContractError as e:
        return _public_failure(e, "分析投入配置冲突，请返回上一步重新确认。", 409, code="effort_snapshot_conflict")
    except Exception as e:
        logger.exception("生成本体定义失败")
        return _public_failure(e, "场景本体生成失败，请稍后重试。")


# ============== 接口2：构建图谱 ==============

@graph_bp.route('/build', methods=['POST'])
def build_graph():
    """
    接口2：根据project_id构建图谱
    
    请求（JSON）：
        {
            "project_id": "proj_xxxx",  // 必填，来自接口1
            "graph_name": "图谱名称",    // 可选
            "chunk_size": 500,          // 可选，默认500
            "chunk_overlap": 50         // 可选，默认50
        }
        
    返回：
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "task_id": "task_xxxx",
                "message": "图谱构建任务已启动"
            }
        }
    """
    try:
        logger.info("=== 开始构建图谱 ===")
        
        # 检查配置
        errors = []
        if not Config.ZEP_API_KEY:
            errors.append("图谱服务尚未配置")
        if errors:
            logger.error(f"配置错误: {errors}")
            return jsonify({
                "success": False,
                "error": "配置错误: " + "; ".join(errors)
            }), 500
        
        # 解析请求
        data = request.get_json() or {}
        project_id = data.get('project_id')
        logger.debug(f"请求参数: project_id={project_id}")
        
        if not project_id:
            return jsonify({
                "success": False,
                "error": "缺少项目信息"
            }), 400
        
        # 获取项目
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": "项目不存在"
            }), 404
        
        # 检查项目状态
        force = data.get('force', False)  # 强制重新构建
        
        if project.status == ProjectStatus.CREATED:
            return jsonify({
                "success": False,
                "error": "项目尚未生成本体，请先完成场景资料分析"
            }), 400
        
        if project.status == ProjectStatus.GRAPH_BUILDING and not force:
            return jsonify({
                "success": False,
                "error": "图谱正在构建中，请勿重复提交",
                "task_id": project.graph_build_task_id
            }), 400
        
        # 如果强制重建，重置状态
        if force and project.status in [ProjectStatus.GRAPH_BUILDING, ProjectStatus.FAILED, ProjectStatus.GRAPH_COMPLETED]:
            project.status = ProjectStatus.ONTOLOGY_GENERATED
            project.graph_id = None
            project.graph_build_task_id = None
            project.error = None
        
        # 获取配置
        graph_name = data.get('graph_name', project.name or 'Envfish 推演图谱')
        chunk_size = data.get('chunk_size', project.chunk_size or Config.DEFAULT_CHUNK_SIZE)
        chunk_overlap = data.get('chunk_overlap', project.chunk_overlap or Config.DEFAULT_CHUNK_OVERLAP)
        
        # 更新项目配置
        project.chunk_size = chunk_size
        project.chunk_overlap = chunk_overlap
        
        # 获取提取的文本
        text = ProjectManager.get_extracted_text(project_id)
        if not text:
            return jsonify({
                "success": False,
                "error": "未找到提取的文本内容"
            }), 400
        
        # 获取本体
        ontology = project.ontology
        if not ontology:
            return jsonify({
                "success": False,
                "error": "未找到本体定义"
            }), 400
        
        # 创建异步任务
        task_manager = TaskManager()
        task_id = task_manager.create_task(
            f"构建图谱: {graph_name}",
            metadata={"project_id": project_id, "graph_name": graph_name},
            task_type="graph_build",
        )
        logger.info(f"创建图谱构建任务: task_id={task_id}, project_id={project_id}")
        
        # 更新项目状态
        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        project.error = None
        ProjectManager.save_project(project)
        
        # 启动后台任务
        def build_task():
            build_logger = get_logger('envfish.build')
            try:
                def ensure_running():
                    task_manager.ensure_not_cancelled(task_id)

                build_logger.info(f"[{task_id}] 开始构建图谱...")
                task_manager.update_task(
                    task_id, 
                    status=TaskStatus.PROCESSING,
                    message="初始化图谱构建服务..."
                )
                ensure_running()
                
                # 创建图谱构建服务
                builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
                
                # 分块
                ensure_running()
                task_manager.update_task(
                    task_id,
                    message="文本分块中...",
                    progress=5
                )
                chunks = TextProcessor.split_text(
                    text, 
                    chunk_size=chunk_size, 
                    overlap=chunk_overlap
                )
                total_chunks = len(chunks)
                
                # 创建图谱
                ensure_running()
                task_manager.update_task(
                    task_id,
                    message="创建推演图谱…",
                    progress=10
                )
                graph_id = builder.create_graph(name=graph_name)
                ensure_running()
                
                # 更新项目的graph_id
                project.graph_id = graph_id
                ProjectManager.save_project(project)
                
                # 设置本体
                ensure_running()
                task_manager.update_task(
                    task_id,
                    message="设置本体定义...",
                    progress=15
                )
                builder.set_ontology(graph_id, ontology)
                ensure_running()
                
                # 添加文本（progress_callback 签名是 (msg, progress_ratio)）
                def add_progress_callback(msg, progress_ratio):
                    ensure_running()
                    progress = 15 + int(progress_ratio * 40)  # 15% - 55%
                    task_manager.update_task(
                        task_id,
                        message=msg,
                        progress=progress
                    )
                
                task_manager.update_task(
                    task_id,
                    message=f"开始添加 {total_chunks} 个文本块...",
                    progress=15
                )
                
                ensure_running()
                episode_uuids = builder.add_text_batches(
                    graph_id, 
                    chunks,
                    batch_size=3,
                    progress_callback=add_progress_callback
                )
                
                # 等待Zep处理完成（查询每个episode的processed状态）
                ensure_running()
                task_manager.update_task(
                    task_id,
                    message="等待图谱引擎处理数据…",
                    progress=55
                )
                
                def wait_progress_callback(msg, progress_ratio):
                    ensure_running()
                    progress = 55 + int(progress_ratio * 35)  # 55% - 90%
                    task_manager.update_task(
                        task_id,
                        message=msg,
                        progress=progress
                    )
                
                builder._wait_for_episodes(episode_uuids, wait_progress_callback)
                
                # 获取图谱数据
                ensure_running()
                task_manager.update_task(
                    task_id,
                    message="获取图谱数据...",
                    progress=95
                )
                graph_data = builder.get_graph_data(graph_id)
                ensure_running()
                
                # 更新项目状态
                project.status = ProjectStatus.GRAPH_COMPLETED
                project.error = None
                ProjectManager.save_project(project)
                
                node_count = graph_data.get("node_count", 0)
                edge_count = graph_data.get("edge_count", 0)
                build_logger.info(f"[{task_id}] 图谱构建完成: graph_id={graph_id}, 节点={node_count}, 边={edge_count}")
                
                # 完成
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED,
                    message="图谱构建完成",
                    progress=100,
                    result={
                        "project_id": project_id,
                        "graph_id": graph_id,
                        "node_count": node_count,
                        "edge_count": edge_count,
                        "chunk_count": total_chunks
                    }
                )
                
            except Exception as e:
                if isinstance(e, TaskCancelledError) or task_manager.is_cancelled(task_id):
                    cancel_reason = str(e) or "用户强制停止"
                    build_logger.info(f"[{task_id}] 图谱构建已取消: {cancel_reason}")
                    project.status = ProjectStatus.FAILED
                    project.error = cancel_reason
                    ProjectManager.save_project(project)
                    return

                # 更新项目状态为失败
                build_logger.error(f"[{task_id}] 图谱构建失败: {str(e)}")
                build_logger.debug(traceback.format_exc())
                
                project.status = ProjectStatus.FAILED
                public_error = public_error_message(e, "图谱构建失败，请稍后重试。")
                project.error = public_error
                ProjectManager.save_project(project)
                
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message=public_error,
                    error=public_error
                )
        
        TaskExecutor(task_manager).start(task_id=task_id, target=build_task)
        
        return jsonify({
            "success": True,
            "data": {
                "project_id": project_id,
                "task_id": task_id,
                "message": "图谱构建任务已启动"
            }
        })
        
    except Exception as e:
        logger.exception("启动图谱构建失败")
        return _public_failure(e, "图谱构建启动失败，请稍后重试。")


# ============== 任务查询接口 ==============

@graph_bp.route('/task/<task_id>', methods=['GET'])
def get_task(task_id: str):
    """
    查询任务状态
    """
    task = TaskManager().get_task(task_id)
    
    if not task:
        return jsonify({
            "success": False,
            "error": "任务不存在"
        }), 404
    
    return _public_success(task.to_dict())


@graph_bp.route('/tasks', methods=['GET'])
def list_tasks():
    """
    列出所有任务
    """
    tasks = TaskManager().list_tasks()
    
    return _public_success([t.to_dict() for t in tasks], count=len(tasks))


# ============== 图谱数据接口 ==============

@graph_bp.route('/data/<graph_id>', methods=['GET'])
def get_graph_data(graph_id: str):
    """
    获取图谱数据（节点和边）
    """
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "图谱服务尚未配置"
            }), 500
        
        builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
        graph_data = builder.get_graph_data(graph_id)
        
        return _public_success(graph_data)
        
    except Exception as e:
        logger.exception("获取图谱数据失败")
        return _public_failure(e, "获取图谱数据失败，请稍后重试。")


@graph_bp.route('/delete/<graph_id>', methods=['DELETE'])
def delete_graph(graph_id: str):
    """
    删除Zep图谱
    """
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "图谱服务尚未配置"
            }), 500
        
        builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
        builder.delete_graph(graph_id)
        
        return jsonify({
            "success": True,
            "message": "图谱已删除"
        })
        
    except Exception as e:
        logger.exception("删除图谱失败")
        return _public_failure(e, "删除图谱失败，请稍后重试。")
