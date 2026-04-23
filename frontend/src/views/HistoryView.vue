<template>
  <div class="history-page">
    <header class="topbar">
      <KaleidoNavBrand to="/" />

      <div class="topbar-links">
        <router-link to="/" class="ghost-link">返回首页</router-link>
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
      <div class="history-content">
        <div class="section-copy">
          <span class="section-kicker">Kaleido History</span>
          <h2>万象推演记录</h2>
          <p>这里记录了所有已完成和进行中的模拟任务，你可以随时回访图谱、环境配置或分析报告。</p>
        </div>
        <HistoryDatabase />
      </div>
    </main>
  </div>
</template>

<script setup>
import HistoryDatabase from '../components/HistoryDatabase.vue'
import KaleidoNavBrand from '../components/KaleidoNavBrand.vue'
</script>

<style scoped>
.history-page {
  min-height: 100vh;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 60px;
  padding: 0 24px;
  backdrop-filter: blur(14px);
  background: rgba(244, 246, 241, 0.92);
  border-bottom: 1px solid rgba(16, 35, 29, 0.08);
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
  background: rgba(255, 255, 255, 0.55);
  color: inherit;
  text-decoration: none;
  cursor: pointer;
  transition: transform 0.24s ease, border-color 0.24s ease, box-shadow 0.24s ease;
  font: inherit;
}

.ghost-link:hover,
.repo-link:hover {
  transform: translateY(-2px);
  background: rgba(255, 255, 255, 0.8);
}

.page-shell {
  max-width: 1320px;
  margin: 0 auto;
  padding: 4rem 2rem;
}

.section-copy {
  margin-bottom: 3rem;
  text-align: center;
}

.section-kicker {
  font-family: 'IBM Plex Mono', monospace;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #1f5d45;
  font-size: 0.9rem;
  display: block;
  margin-bottom: 0.5rem;
}

.section-copy h2 {
  font-family: 'Fraunces', 'Noto Serif SC', serif;
  font-size: 2.5rem;
  margin-bottom: 1rem;
  color: #11281f;
}

.section-copy p {
  max-width: 600px;
  margin: 0 auto;
  color: rgba(23, 49, 38, 0.74);
  line-height: 1.6;
}
</style>
