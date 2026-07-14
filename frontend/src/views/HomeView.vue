<template>
  <div class="env-home">
    <header class="topbar">
      <KaleidoNavBrand @click="scrollTop" />
      <nav class="topbar-links">
        <button class="ghost-link" type="button" @click="openComposer">进入推演</button>
        <button class="ghost-link demo-link" type="button" :disabled="restoringDemo" @click="playWuhanDemo">
          {{ restoringDemo ? '正在恢复演示...' : '武汉疫情演示' }}
        </button>
        <RouterLink to="/space-forecast" class="ghost-link">太空预测</RouterLink>
        <RouterLink to="/history" class="ghost-link">历史记录</RouterLink>
      </nav>
    </header>

    <main class="page-shell">
      <section class="hero-section">
        <div class="hero-content">
          <div class="eyebrow-row">
            <span class="eyebrow-pill">生态推演引擎</span>
            <span class="eyebrow-note">Kaleido v0.1</span>
          </div>
          <h1 class="hero-title">KALEIDO</h1>
          <p class="hero-tagline">万象生态推演：把环境变量丢进沙盘，让系统自己演化。</p>
          <div class="hero-actions">
            <button class="primary-cta" type="button" @click="openComposer">开启推演流程</button>
            <button class="secondary-cta" type="button" :disabled="restoringDemo" @click="playWuhanDemo">
              {{ restoringDemo ? '正在恢复演示...' : '播放武汉疫情演示' }}
            </button>
          </div>
        </div>
      </section>

      <section class="intro-section">
        <div class="section-copy">
          <span class="section-kicker">01 / 推演流程</span>
          <h2>标准化的生态推演流程</h2>
          <p>图谱构建、环境搭建、模拟、报告和互动能力仍然沿用现有工作台；每一部分都为您提供深度的生态洞察。</p>
        </div>
        <div class="workflow-grid">
          <article v-for="item in workflow" :key="item.id" class="workflow-card">
            <span class="workflow-id">{{ item.id }}</span>
            <h3>{{ item.title }}</h3>
            <p>{{ item.desc }}</p>
          </article>
        </div>
      </section>

      <section class="intro-section alt-bg">
        <div class="section-copy">
          <span class="section-kicker">02 / 场景模板</span>
          <h2>先选一个生态切口，再把变量写进系统。</h2>
          <p>下方模板只负责起笔。真正的输入仍然是你的材料与约束条件，系统会引导您逐步细化推演规则。</p>
        </div>
        <div class="prompt-grid">
          <button v-for="item in prompts" :key="item.title" class="prompt-card" type="button" @click="openComposer">
            <span class="prompt-type">{{ item.type }}</span>
            <strong>{{ item.title }}</strong>
            <p>{{ item.desc }}</p>
          </button>
        </div>
      </section>

      <section id="launch-composer" class="launch-section">
        <div class="section-copy launch-section-copy">
          <span class="section-kicker">03 / 开始搭建</span>
          <h2>场景生成流程，一眼看完。</h2>
          <p>先把场景素材整理完整，再进入正式推演。第一步会围绕地图锚点、稳态背景、参考资料和素材报告四个环节逐步完成场景搭建。</p>
        </div>
        <div class="process-grid showcase-grid">
          <article v-for="item in launchSteps" :key="item.id" class="process-card">
            <span class="process-id">{{ item.id }}</span>
            <h4>{{ item.title }}</h4>
            <p class="process-what">{{ item.what }}</p>
            <p class="process-action">{{ item.action }}</p>
          </article>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import KaleidoNavBrand from '../components/KaleidoNavBrand.vue'

const router = useRouter()
const restoringDemo = ref(false)

const prompts = [
  { type: '湿地', title: '湿地修复推演', desc: '评估治理计划、极端天气和游客密度叠加后的生态走向。' },
  { type: '流域', title: '流域协同治理', desc: '观察上游排污、工业调整和公共传播如何共同影响系统。' },
  { type: '海岸带', title: '海岸带风险联动', desc: '把产业、灾害和资源调度放进同一张生态沙盘。' }
]

const workflow = [
  { id: '01', title: '背景定义', desc: '基于地图锚点、稳态背景和参考资料，自动生成场景素材报告。' },
  { id: '02', title: '场景生成', desc: '抽取角色、场景与资源约束，把变量真正注入环境。' },
  { id: '03', title: '推演运行', desc: '按轮次推进系统演化，持续记录冲突、扩散和反馈。' },
  { id: '04', title: '分析与报告', desc: '自动归纳演化路径，并与报告智能体或模拟角色深度对话。' }
]

const launchSteps = [
  { id: '01', title: '地图选点', what: '在地图上锁定场景中心点和空间范围，让后续分析有明确地理锚点。', action: '要做什么：输入地点或直接点图，确定分析半径与关注区域。' },
  { id: '02', title: '稳态信息输入', what: '补充时间背景、常态结构和关键约束，让系统知道这个场景平时如何运作。', action: '要做什么：填写地点背景、稳态描述、变量线索和重点关系。' },
  { id: '03', title: '参考资料上传', what: '上传 PDF、Markdown 或文本材料，把真实资料里的地点、主体和事件作为生成依据。', action: '要做什么：补齐新闻、报告、研究材料或现场文档。' },
  { id: '04', title: '素材报告生成', what: '把地图事实、稳态输入和参考资料整理成一份可预览、可修改的场景素材报告。', action: '要做什么：检查报告结构，确认后进入正式推演。' }
]

function scrollTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function openComposer() {
  router.push({ name: 'SceneComposer' })
}

async function playWuhanDemo() {
  if (restoringDemo.value) return
  restoringDemo.value = true
  try {
    await router.push({ name: 'WuhanDemo' })
  } finally {
    restoringDemo.value = false
  }
}
</script>

<style scoped>
html {
  scroll-behavior: smooth;
}

.env-home {
  position: relative;
  min-height: 100vh;
  overflow-x: hidden;
}

.topbar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 60px;
  padding: 0 24px;
  background: rgba(247, 244, 234, 0.68);
  backdrop-filter: blur(14px);
}

.topbar-links {
  display: flex;
  align-items: center;
  gap: 0.85rem;
}

.ghost-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 2.5rem;
  padding: 0 1rem;
  border-radius: 999px;
  border: 1px solid rgba(23, 49, 38, 0.12);
  background: rgba(255, 255, 255, 0.52);
  color: inherit;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.24s ease;
  font-size: 0.875rem;
  font-weight: 600;
}

.ghost-link:hover {
  transform: translateY(-2px);
  background: rgba(255, 255, 255, 0.88);
  border-color: #1f5d45;
}

.page-shell {
  max-width: 1440px;
  margin: 0 auto;
  padding: 0 4rem 8rem;
}

.hero-section {
  min-height: calc(80vh + 60px);
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.eyebrow-row {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.56);
  color: #1f5d45;
  font-size: 13px;
  font-weight: 800;
}

.eyebrow-note {
  color: rgba(23, 49, 38, 0.58);
}

.hero-title {
  font-family: Fraunces, Georgia, serif;
  font-size: clamp(4rem, 12vw, 10rem);
  line-height: 1;
  letter-spacing: 0;
  margin: 1.5rem 0;
  color: #11281f;
}

.hero-tagline {
  font-size: 1.5rem;
  color: rgba(23, 49, 38, 0.65);
  margin-bottom: 3rem;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 1rem;
}

.primary-cta,
.secondary-cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.primary-cta {
  font-size: 1.2rem;
  padding: 1.2rem 3rem;
  border: none;
  background: linear-gradient(135deg, #1f5d45, #82a95f);
  color: #fff;
  box-shadow: 0 1.5rem 3rem rgba(31, 93, 69, 0.2);
}

.secondary-cta {
  font-size: 1.05rem;
  padding: 1.05rem 2.4rem;
  background: rgba(255, 255, 255, 0.68);
  color: #173126;
  border: 1px solid rgba(23, 49, 38, 0.16);
  backdrop-filter: blur(12px);
}

.primary-cta:hover {
  transform: scale(1.04) translateY(-4px);
  box-shadow: 0 2rem 4rem rgba(31, 93, 69, 0.3);
}

.secondary-cta:hover {
  transform: translateY(-3px);
  border-color: #1f5d45;
}

.intro-section {
  padding: 8rem 0;
}

.intro-section.alt-bg {
  background: rgba(255, 255, 255, 0.38);
  margin: 0 -100vw;
  padding: 8rem 100vw;
}

.section-copy {
  max-width: 800px;
  margin: 0 auto 5rem;
  text-align: center;
}

.section-kicker {
  font-family: IBM Plex Mono, JetBrains Mono, monospace;
  text-transform: uppercase;
  color: #1f5d45;
  font-weight: 700;
  display: block;
  margin-bottom: 1rem;
}

.section-copy h2 {
  font-family: Fraunces, Georgia, serif;
  font-size: 3rem;
  margin-bottom: 1.5rem;
  color: #11281f;
}

.section-copy p {
  font-size: 1.15rem;
  line-height: 1.7;
  color: rgba(23, 49, 38, 0.72);
}

.workflow-grid,
.process-grid {
  display: grid;
  gap: 1.5rem;
}

.workflow-grid {
  grid-template-columns: repeat(4, 1fr);
}

.workflow-card,
.process-card,
.prompt-card {
  background: rgba(255, 255, 255, 0.68);
  border: 1px solid rgba(23, 49, 38, 0.08);
  transition: all 0.3s ease;
}

.workflow-card {
  padding: 2rem;
  border-radius: 8px;
}

.workflow-card:hover,
.prompt-card:hover {
  transform: translateY(-8px);
  background: #fff;
  box-shadow: 0 2rem 4rem rgba(0, 0, 0, 0.05);
}

.workflow-id,
.prompt-type,
.process-id {
  font-family: IBM Plex Mono, JetBrains Mono, monospace;
  color: #1f5d45;
}

.workflow-id {
  font-size: 0.85rem;
  margin-bottom: 1rem;
  display: block;
}

.workflow-card h3,
.prompt-card strong,
.process-card h4 {
  font-family: Fraunces, Georgia, serif;
  color: #11281f;
}

.workflow-card h3 {
  margin-bottom: 1rem;
  font-size: 1.25rem;
}

.workflow-card p,
.prompt-card p {
  font-size: 0.95rem;
  line-height: 1.6;
  color: rgba(23, 49, 38, 0.62);
}

.prompt-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 2rem;
}

.prompt-card {
  text-align: left;
  padding: 2.5rem;
  border-radius: 8px;
  cursor: pointer;
}

.prompt-type {
  font-size: 0.8rem;
  margin-bottom: 1rem;
  display: block;
}

.prompt-card strong {
  font-size: 1.5rem;
  display: block;
  margin-bottom: 1rem;
}

.launch-section {
  display: grid;
  gap: 4rem;
  padding: 12rem 0;
  justify-items: center;
}

.launch-section-copy {
  margin-bottom: 0;
}

.process-grid {
  width: 100%;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.showcase-grid {
  max-width: 1320px;
}

.process-card {
  min-height: 240px;
  padding: 1.75rem;
  border-radius: 8px;
  box-shadow: 0 2rem 4rem rgba(31, 50, 40, 0.08);
}

.process-id {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 3.2rem;
  height: 2rem;
  padding: 0 0.8rem;
  border-radius: 999px;
  background: rgba(31, 93, 69, 0.1);
  font-size: 0.8rem;
  font-weight: 700;
  margin-bottom: 1rem;
}

.process-card h4 {
  font-size: 1.55rem;
  margin-bottom: 1rem;
}

.process-what,
.process-action {
  line-height: 1.75;
  color: rgba(23, 49, 38, 0.74);
}

.process-action {
  margin-top: 1rem;
  color: #1f5d45;
  font-weight: 700;
}

@media (max-width: 1100px) {
  .workflow-grid,
  .process-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 900px) {
  .prompt-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .page-shell {
    padding: 0 1rem 6rem;
  }

  .topbar {
    padding: 0 16px;
  }

  .topbar-links {
    gap: 0.5rem;
  }

  .ghost-link {
    min-height: 2.3rem;
    padding: 0 0.85rem;
    font-size: 0.8rem;
  }

  .process-grid,
  .workflow-grid {
    grid-template-columns: 1fr;
  }
}
</style>
