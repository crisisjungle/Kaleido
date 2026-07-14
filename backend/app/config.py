"""
配置管理
统一从项目根目录的 .env 文件加载配置
"""

import os
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件
# 路径: Kaleido/.env (相对于 backend/app/config.py)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    # 如果根目录没有 .env，尝试加载环境变量（用于生产环境）
    load_dotenv(override=True)


class Config:
    """Flask配置类"""
    
    # Flask配置
    SECRET_KEY = os.environ.get('SECRET_KEY', 'kaleido-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    
    # JSON配置 - 禁用ASCII转义，让中文直接显示（而不是 \uXXXX 格式）
    JSON_AS_ASCII = False
    
    # LLM配置（统一使用OpenAI格式）
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')
    LLM_FALLBACK_API_KEY = os.environ.get('LLM_FALLBACK_API_KEY')
    LLM_FALLBACK_BASE_URL = os.environ.get('LLM_FALLBACK_BASE_URL', LLM_BASE_URL)
    LLM_FALLBACK_MODEL_NAME = os.environ.get('LLM_FALLBACK_MODEL_NAME', LLM_MODEL_NAME)
    # DeepSeek V4 兼容配置：
    # - auto: 对 deepseek-chat / deepseek-reasoner 使用兼容映射；
    #         对显式的 V4 模型名沿用官方默认行为
    # - enabled / disabled: 强制指定思考模式
    DEEPSEEK_THINKING_MODE = os.environ.get('DEEPSEEK_THINKING_MODE', 'auto')
    DEEPSEEK_REASONING_EFFORT = os.environ.get('DEEPSEEK_REASONING_EFFORT', 'high')
    
    # Zep配置
    ZEP_API_KEY = os.environ.get('ZEP_API_KEY')
    
    # 文件上传配置
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}

    # 地图公网数据源。公共 Overpass 实例只适合轻量查询；生产环境可通过
    # OVERPASS_ENDPOINTS 指向自托管/受控实例，多个地址使用逗号分隔。
    OVERPASS_ENDPOINTS = [
        item.strip()
        for item in os.environ.get(
            'OVERPASS_ENDPOINTS',
            'https://overpass-api.de/api/interpreter,https://lz4.overpass-api.de/api/interpreter',
        ).split(',')
        if item.strip()
    ]
    OVERPASS_QUERY_TIMEOUT_SECONDS = int(os.environ.get('OVERPASS_QUERY_TIMEOUT_SECONDS', '12'))
    OVERPASS_HTTP_TIMEOUT_SECONDS = int(os.environ.get('OVERPASS_HTTP_TIMEOUT_SECONDS', '15'))
    # Each thematic query is intentionally small, but regional AOIs can still
    # exceed Overpass's 32 MiB default working-memory declaration.
    OVERPASS_MAXSIZE_BYTES = int(os.environ.get('OVERPASS_MAXSIZE_BYTES', str(64 * 1024 * 1024)))
    MAP_SOURCE_CACHE_TTL_SECONDS = int(os.environ.get('MAP_SOURCE_CACHE_TTL_SECONDS', str(7 * 24 * 3600)))
    # Terrascope retired the legacy ``services.terrascope.be/wms/v2`` contract.
    # The official WorldCover data-access page now points to the TiTiler WMS
    # endpoint and its 1.3.0 layer identifiers.
    WORLDCOVER_WMS_URL = os.environ.get('WORLDCOVER_WMS_URL', 'https://titiler.terrascope.be/wms')
    WORLDCOVER_WMS_VERSION = os.environ.get('WORLDCOVER_WMS_VERSION', '1.3.0')
    WORLDCOVER_WMS_LAYER = os.environ.get(
        'WORLDCOVER_WMS_LAYER',
        'esa-worldcover-map-10m-2021-v2_map',
    )
    WORLDCOVER_WMS_TIME = os.environ.get('WORLDCOVER_WMS_TIME', '2021-01-01')
    WORLDCOVER_WMS_TIMEOUT_SECONDS = int(os.environ.get('WORLDCOVER_WMS_TIMEOUT_SECONDS', '10'))
    WORLDCOVER_WMS_ATTEMPTS = int(os.environ.get('WORLDCOVER_WMS_ATTEMPTS', '1'))
    
    # 文本处理配置
    DEFAULT_CHUNK_SIZE = 500  # 默认切块大小
    DEFAULT_CHUNK_OVERLAP = 50  # 默认重叠大小
    
    # OASIS模拟配置
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')
    
    # OASIS平台可用动作配置
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]
    
    # 冻结黄金案例/脚手架工件目录
    GOLDEN_RUNS_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads/golden_runs')

    # EnvFish 推演架构。默认保留旧链路；开发/选定案例可显式启用 llm_mechanism_v1。
    ENVFISH_SIMULATION_ARCHITECTURE = os.environ.get('ENVFISH_SIMULATION_ARCHITECTURE', 'legacy_envfish_v1')
    # 风险对象契约。新建模拟默认使用机制路径驱动的 V2；设为 1 可紧急回退旧模板生成。
    RISK_OBJECT_CONTRACT_VERSION = int(os.environ.get('RISK_OBJECT_CONTRACT_VERSION', '2'))
    
    # Report Agent配置
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))
    
    @classmethod
    def validate(cls):
        """验证必要配置"""
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY 未配置")
        if not cls.ZEP_API_KEY:
            errors.append("ZEP_API_KEY 未配置")
        return errors
