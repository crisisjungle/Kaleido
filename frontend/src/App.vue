<template>
  <div class="app-background">
    <div
      v-for="ball in balls"
      :key="ball.id"
      class="ambient"
      :class="ball.class"
      :style="{
        transform: `translate(${ball.x}px, ${ball.y}px)`,
        width: `${ball.size}px`,
        height: `${ball.size}px`
      }"
    ></div>
  </div>
  <router-view />
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
const balls = ref([
  { id: 'a', class: 'ambient-a', x: 0, y: 0, vx: 0.5, vy: 0.6, size: 320 },
  { id: 'b', class: 'ambient-b', x: 200, y: 300, vx: -0.4, vy: 0.7, size: 384 },
  { id: 'c', class: 'ambient-c', x: 400, y: 100, vx: 0.6, vy: -0.5, size: 288 }
])

let animationFrame

const updateBalls = () => {
  const width = window.innerWidth
  const height = window.innerHeight

  balls.value.forEach(ball => {
    ball.x += ball.vx
    ball.y += ball.vy

    // Bounce off edges (partially off-screen)
    const margin = ball.size / 2
    if (ball.x < -margin || ball.x > width - margin) {
      ball.vx *= -1
      // Bring back slightly to prevent sticking
      ball.x += ball.vx * 2
    }
    if (ball.y < -margin || ball.y > height - margin) {
      ball.vy *= -1
      // Bring back slightly to prevent sticking
      ball.y += ball.vy * 2
    }
    
    // Safety check to keep them from disappearing completely if resized
    if (ball.x < -ball.size) ball.x = -ball.size
    if (ball.x > width) ball.x = width
    if (ball.y < -ball.size) ball.y = -ball.size
    if (ball.y > height) ball.y = height
  })

  animationFrame = requestAnimationFrame(updateBalls)
}

onMounted(() => {
  // Initialize positions randomly within viewport
  balls.value.forEach(ball => {
    ball.x = Math.random() * (window.innerWidth - ball.size / 2)
    ball.y = Math.random() * (window.innerHeight - ball.size / 2)
  })
  updateBalls()
})

onUnmounted(() => {
  cancelAnimationFrame(animationFrame)
})
</script>

<style>
html,
body,
#app {
  min-height: 100%;
}

/* 全局样式重置 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

#app {
  font-family: 'IBM Plex Sans', 'Noto Sans SC', sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: #173126;
  position: relative;
}

/* 全局背景 */
body {
  background:
    radial-gradient(circle at top left, rgba(191, 214, 167, 0.48), transparent 34%),
    radial-gradient(circle at right 20%, rgba(217, 176, 120, 0.26), transparent 30%),
    linear-gradient(180deg, #f7f4ea 0%, #efe9da 48%, #f5efe2 100%);
  background-attachment: fixed;
}

.app-background {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: -1;
  overflow: hidden;
  pointer-events: none;
}

.ambient {
  position: absolute;
  top: 0;
  left: 0;
  border-radius: 999px;
  filter: blur(40px);
  opacity: 0.6;
  pointer-events: none;
  will-change: transform;
}

.ambient-a {
  background: rgba(153, 193, 118, 0.38);
}

.ambient-b {
  background: rgba(41, 108, 77, 0.16);
}

.ambient-c {
  background: rgba(230, 193, 113, 0.22);
}

/* 滚动条样式 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: rgba(23, 49, 38, 0.08);
}

::-webkit-scrollbar-thumb {
  background: rgba(31, 93, 69, 0.6);
  border-radius: 999px;
}

::-webkit-scrollbar-thumb:hover {
  background: rgba(31, 93, 69, 0.8);
}

button {
  font-family: inherit;
}
</style>
