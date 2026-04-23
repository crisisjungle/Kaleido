<template>
  <div class="env-home">
    <header class="topbar">
      <KaleidoNavBrand @click="scrollToTop" />

      <div class="topbar-links">
        <button v-if="showFullWorkflow" class="ghost-link" type="button" @click="openSceneComposer">进入推演</button>
        <router-link to="/space-forecast" class="ghost-link">太空预测</router-link>
        <router-link v-if="showFullWorkflow" to="/history" class="ghost-link">历史记录</router-link>
        <a
          class="repo-link"
          href="https://github.com/crisisjungle/Kaleido"
          target="_blank"
          rel="noreferrer"
        >
          GitHub ↗
        </a>
      </div>
    </header>

    <main class="page-shell">
      <!-- HERO SECTION -->
      <section class="hero-section">
        <div class="hero-content">
          <div class="eyebrow-row">
            <span class="eyebrow-pill">生态推演引擎</span>
            <span class="eyebrow-note">Kaleido v0.1</span>
          </div>

          <h1 class="hero-title">KALEIDO</h1>
          <p class="hero-tagline">万象生态推演：把环境变量丢进沙盘，让系统自己演化。</p>

          <div class="hero-actions">
            <button v-if="showFullWorkflow" class="primary-cta" type="button" @click="openSceneComposer">
              开启推演流程
            </button>
            <router-link v-else to="/space-forecast" class="primary-cta">
              进入太空碰撞模拟
            </router-link>
          </div>
        </div>
      </section>

      <!-- STEP 1: WORKFLOW -->
      <section class="intro-section">
        <div class="section-copy">
          <span class="section-kicker">01 / Process</span>
          <h2>标准化的生态推演流程</h2>
          <p>
            图谱构建、环境搭建、模拟、报告和互动能力仍然沿用现有工作台；每一部分都为您提供深度的生态洞察。
          </p>
        </div>

        <div class="workflow-grid">
          <article v-for="step in workflowSteps" :key="step.id" class="workflow-card">
            <span class="workflow-id">{{ step.id }}</span>
            <h3>{{ step.title }}</h3>
            <p>{{ step.desc }}</p>
          </article>
        </div>
      </section>

      <!-- STEP 2: PROMPTS -->
      <section class="intro-section alt-bg">
        <div class="section-copy">
          <span class="section-kicker">02 / Templates</span>
          <h2>先选一个生态切口，再把变量写进系统。</h2>
          <p>
            下方模板只负责起笔。真正的输入仍然是你的材料与约束条件，系统会引导您逐步细化推演规则。
          </p>
        </div>

        <div class="prompt-grid">
          <button
            v-for="idea in promptIdeas"
            :key="idea.title"
            class="prompt-card"
            type="button"
            @click="applyPrompt(idea.prompt)"
          >
            <span class="prompt-type">{{ idea.type }}</span>
            <strong>{{ idea.title }}</strong>
            <p>{{ idea.desc }}</p>
          </button>
        </div>
      </section>

      <!-- FINAL STEP: LAUNCH CONSOLE -->
      <section id="launch-composer" class="launch-section">
        <div class="section-copy launch-section-copy">
          <span class="section-kicker">03 / Launch</span>
          <h2>场景生成流程，一眼看完。</h2>
          <p>
            先把场景素材整理完整，再进入正式推演。step1 会围绕地图锚点、稳态背景、参考资料和素材报告四个环节逐步完成场景搭建。
          </p>
        </div>

        <div class="process-grid showcase-grid">
          <article v-for="step in sceneSeedSteps" :key="step.id" class="process-card">
            <span class="process-id">{{ step.id }}</span>
            <h4>{{ step.title }}</h4>
            <p class="process-what">{{ step.what }}</p>
            <p class="process-action">{{ step.action }}</p>
          </article>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import KaleidoNavBrand from '../components/KaleidoNavBrand.vue'

const router = useRouter()
const launchMode = import.meta.env.VITE_PUBLIC_LAUNCH_MODE || 'full'
const showFullWorkflow = launchMode !== 'space_only'

const promptIdeas = [
  {
    type: 'Wetland',
    title: '湿地修复推演',
    desc: '评估治理计划、极端天气和游客密度叠加后的生态走向。',
    prompt: '围绕一项滨海湿地修复计划进行生态推演：请综合考虑极端天气、游客增长和污染治理预算波动，分析不同主体互动后生态网络的演化趋势。'
  },
  {
    type: 'River',
    title: '流域协同治理',
    desc: '观察上游排污、工业调整和公共传播如何共同影响系统。',
    prompt: '针对流域协同治理场景，模拟上游排污反弹、地方产业转型和环保宣传同步发生时，不同参与者关系与环境指标会怎样变化。'
  },
  {
    type: 'Coastline',
    title: '海岸带风险联动',
    desc: '把产业、灾害和资源调度放进同一张生态沙盘。',
    prompt: '建立一个海岸带生态推演场景，加入风暴潮预警、港口扩容和渔业资源恢复计划三个变量，预测系统稳定性与利益博弈的变化。'
  }
]
const workflowSteps = [
  { id: '01', title: '图谱构建', desc: '把现实材料拆成实体、关系与时序记忆，为后续生态推演建立骨架。' },
  { id: '02', title: '环境搭建', desc: '抽取角色、场景与资源约束，把变量真正注入环境。' },
  { id: '03', title: '开始模拟', desc: '按轮次推进系统演化，持续记录冲突、扩散和反馈。' },
  { id: '04', title: '报告生成', desc: '自动归拿演化路径、关键拐点和可操作建议。' },
  { id: '05', title: '深度互动', desc: '继续和报告智能体或模拟角色对话，追问细节。' }
]
const sceneSeedSteps = [
  {
    id: '01',
    title: '地图选点',
    what: '在地图上锁定场景中心点和空间范围，让后续分析有明确地理锚点。',
    action: '要做什么：输入地点或直接点图，确定分析半径与关注区域。'
  },
  {
    id: '02',
    title: '稳态信息输入',
    what: '补充时间背景、常态结构和关键约束，让系统知道这个场景平时如何运作。',
    action: '要做什么：填写地点背景、稳态描述、变量线索和重点关系。'
  },
  {
    id: '03',
    title: '参考资料上传',
    what: '上传 PDF、Markdown 或文本材料，把真实资料里的地点、主体和事件作为生成依据。',
    action: '要做什么：补齐新闻、报告、研究材料或现场文档。'
  },
  {
    id: '04',
    title: '素材报告生成',
    what: '把地图事实、稳态输入和参考资料整理成一份可预览、可修改的场景素材报告。',
    action: '要做什么：检查报告结构，确认后进入正式推演。'
  }
]
const scrollToTop = () => {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

const applyPrompt = (prompt) => {
  void prompt
  openSceneComposer()
}

const openSceneComposer = () => {
  router.push({
    name: 'SceneComposer'
  })
}

</script>

<style scoped>
:global(html) {
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
  background: transparent;
}

.topbar-links {
  display: flex;
  align-items: center;
  gap: 0.85rem;
}

.ghost-link,
.repo-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 2.5rem;
  padding: 0 1rem;
  border-radius: 999px;
  border: 1px solid rgba(23, 49, 38, 0.12);
  background: rgba(255, 255, 255, 0.3);
  backdrop-filter: blur(10px);
  color: inherit;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.24s ease;
  font-size: 0.875rem;
  font-weight: 500;
}

.ghost-link:hover,
.repo-link:hover {
  transform: translateY(-2px);
  background: rgba(255, 255, 255, 0.85);
  border-color: #1f5d45;
}

.page-shell {
  max-width: 1440px;
  margin: 0 auto;
  padding: 0 4rem 8rem;
}

/* HERO */
.hero-section {
  min-height: calc(80vh + 60px);
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.hero-title {
  font-family: 'Fraunces', serif;
  font-size: clamp(4rem, 12vw, 10rem);
  line-height: 1;
  letter-spacing: -0.05em;
  margin: 1.5rem 0;
  color: #11281f;
}

.hero-tagline {
  font-size: 1.5rem;
  color: rgba(23, 49, 38, 0.65);
  margin-bottom: 3rem;
}

.hero-actions .primary-cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 1.2rem;
  padding: 1.2rem 3rem;
  background: linear-gradient(135deg, #1f5d45, #82a95f);
  color: #fff;
  text-decoration: none;
  border: none;
  border-radius: 999px;
  cursor: pointer;
  box-shadow: 0 1.5rem 3rem rgba(31, 93, 69, 0.2);
  transition: all 0.3s ease;
}

.hero-actions .primary-cta:hover {
  transform: scale(1.05) translateY(-5px);
  box-shadow: 0 2rem 4rem rgba(31, 93, 69, 0.3);
}

/* INTRO SECTIONS */
.intro-section {
  padding: 8rem 0;
}

.intro-section.alt-bg {
  background: rgba(255, 255, 255, 0.3);
  margin: 0 -100vw;
  padding: 8rem 100vw;
}

.section-copy {
  max-width: 800px;
  margin: 0 auto 5rem;
  text-align: center;
}

.section-kicker {
  font-family: 'IBM Plex Mono', monospace;
  text-transform: uppercase;
  color: #1f5d45;
  font-weight: 600;
  display: block;
  margin-bottom: 1rem;
}

.section-copy h2 {
  font-family: 'Fraunces', serif;
  font-size: 3rem;
  margin-bottom: 1.5rem;
  color: #11281f;
}

.section-copy p {
  font-size: 1.15rem;
  line-height: 1.7;
  color: rgba(23, 49, 38, 0.7);
}

/* WORKFLOW */
.workflow-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 1.5rem;
}

.workflow-card {
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(23, 49, 38, 0.08);
  padding: 2rem;
  border-radius: 1.5rem;
  transition: all 0.3s ease;
}

.workflow-card:hover {
  transform: translateY(-10px);
  background: #fff;
  box-shadow: 0 2rem 4rem rgba(0, 0, 0, 0.05);
}

.workflow-id {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.85rem;
  color: #1f5d45;
  margin-bottom: 1rem;
  display: block;
}

.workflow-card h3 {
  font-family: 'Fraunces', serif;
  margin-bottom: 1rem;
  font-size: 1.25rem;
}

.workflow-card p {
  font-size: 0.95rem;
  line-height: 1.6;
  color: rgba(23, 49, 38, 0.6);
}

/* PROMPTS */
.prompt-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 2rem;
}

.prompt-card {
  text-align: left;
  background: #fff;
  padding: 2.5rem;
  border-radius: 2rem;
  border: 1px solid rgba(23, 49, 38, 0.05);
  cursor: pointer;
  transition: all 0.3s ease;
}

.prompt-card:hover {
  transform: scale(1.02);
  box-shadow: 0 3rem 6rem rgba(31, 93, 69, 0.1);
}

.prompt-type {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.8rem;
  color: #82a95f;
  margin-bottom: 1rem;
  display: block;
}

.prompt-card strong {
  font-family: 'Fraunces', serif;
  font-size: 1.5rem;
  display: block;
  margin-bottom: 1rem;
}

/* LAUNCH */
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
  display: grid;
  width: 100%;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 2rem;
}

.showcase-grid {
  max-width: 1320px;
}

.process-card {
  position: relative;
  min-height: 240px;
  padding: 1.75rem;
  border-radius: 2rem;
  background: rgba(255, 255, 255, 0.84);
  border: 1px solid rgba(23, 49, 38, 0.06);
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
  color: #1f5d45;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.8rem;
  font-weight: 700;
  margin-bottom: 1rem;
}

.process-card h4 {
  font-family: 'Fraunces', serif;
  font-size: 1.55rem;
  margin-bottom: 1rem;
  color: #11281f;
}

.process-what,
.process-action {
  line-height: 1.75;
  color: rgba(23, 49, 38, 0.74);
}

.process-action {
  margin-top: 1rem;
  color: #1f5d45;
  font-weight: 600;
}

@media (max-width: 1100px) {
  .workflow-grid {
    grid-template-columns: repeat(3, 1fr);
  }

  .process-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
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

  .ghost-link,
  .repo-link {
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
