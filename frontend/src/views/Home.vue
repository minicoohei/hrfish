<template>
  <div class="home-container">
    <!-- Top navigation bar -->
    <nav class="navbar">
      <div class="nav-brand">HR CAREER SIM</div>
      <div class="nav-links">
        <a href="https://github.com/666ghj/MiroFish" target="_blank" class="github-link">
          GitHub <span class="arrow">↗</span>
        </a>
      </div>
    </nav>

    <div class="main-content">
      <!-- Hero Section -->
      <section class="hero-section">
        <div class="hero-left">
          <div class="tag-row">
            <span class="orange-tag">AI搭載 HRキャリアシミュレーター</span>
            <span class="version-text">/ v0.1-preview</span>
          </div>
          
          <h1 class=”main-title”>
            履歴書をアップロードして<br>
            <span class=”gradient-text”>キャリアパスをシミュレーション</span>
          </h1>

          <div class=”hero-desc”>
            <p>
              1つの履歴書から、<span class=”highlight-bold”>HRキャリアシミュレーター</span>が<span class=”highlight-orange”>ステークホルダーエージェント</span>（採用担当、人事、経営層、業界アナリスト）の世界を生成し、あらゆる角度からキャリアを評価して<span class=”highlight-code”>”隠れた可能性”</span>を明らかにします。
            </p>
            <p class=”slogan-text”>
              次のキャリアを決める前に、AIステークホルダーに評価してもらおう<span class=”blinking-cursor”>_</span>
            </p>
          </div>
           
          <div class="decoration-square"></div>
        </div>
        
        <div class="hero-right">
          <!-- Logo area -->
          <div class="logo-container">
            <img src="../assets/logo/MiroFish_logo_left.jpeg" alt="MiroFish Logo" class="hero-logo" />
          </div>
          
          <button class="scroll-down-btn" @click="scrollToBottom">
            ↓
          </button>
        </div>
      </section>

      <!-- Bottom half: dual-column layout -->
      <section class="dashboard-section">
        <!-- Left column: status and steps -->
        <div class="left-panel">
          <div class="panel-header">
            <span class="status-dot">■</span> システムステータス
          </div>

          <h2 class="section-title">準備完了</h2>
          <p class="section-desc">
            キャリアシミュレーションエンジン待機中。履歴書をアップロードしてマルチステークホルダー評価を開始
          </p>
          
          <!-- Data metrics cards -->
          <div class="metrics-row">
            <div class="metric-card">
              <div class="metric-value">6+ 役割</div>
              <div class="metric-label">採用担当、人事、経営層、アナリスト...</div>
            </div>
            <div class="metric-card">
              <div class="metric-value">360° 評価</div>
              <div class="metric-label">マルチステークホルダーによるキャリア評価</div>
            </div>
          </div>

          <!-- Project simulation steps intro -->
          <div class="steps-container">
            <div class="steps-header">
               <span class="diamond-icon">◇</span> ワークフロー
            </div>
            <div class="workflow-list">
              <div class="workflow-item">
                <span class="step-num">01</span>
                <div class="step-info">
                  <div class="step-title">履歴書分析</div>
                  <div class="step-desc">スキル抽出、キャリアグラフ構築、ステークホルダー知識ベース生成</div>
                </div>
              </div>
              <div class="workflow-item">
                <span class="step-num">02</span>
                <div class="step-info">
                  <div class="step-title">ステークホルダー設定</div>
                  <div class="step-desc">採用担当、人事、経営層、アナリストのペルソナと評価基準を生成</div>
                </div>
              </div>
              <div class="workflow-item">
                <span class="step-num">03</span>
                <div class="step-info">
                  <div class="step-title">キャリアシミュレーション</div>
                  <div class="step-desc">マルチエージェント並列評価、キャリアパス分析、市場適合性評価</div>
                </div>
              </div>
              <div class="workflow-item">
                <span class="step-num">04</span>
                <div class="step-info">
                  <div class="step-title">キャリアレポート</div>
                  <div class="step-desc">総合キャリア分析: 可能性、ステークホルダー評価、リスキリング方向性</div>
                </div>
              </div>
              <div class="workflow-item">
                <span class="step-num">05</span>
                <div class="step-info">
                  <div class="step-title">コンサルテーション</div>
                  <div class="step-desc">ステークホルダーエージェントと対話 — 採用担当、人事、キャリアコーチに直接質問</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Right column: interactive console -->
        <div class="right-panel">
          <div class="console-box">
            <!-- Upload area -->
            <div class="console-section">
              <div class="console-header">
                <span class="console-label">01 / 履歴書</span>
                <span class="console-meta">対応形式: PDF, MD, TXT</span>
              </div>
              
              <div 
                class="upload-zone"
                :class="{ 'drag-over': isDragOver, 'has-files': files.length > 0 }"
                @dragover.prevent="handleDragOver"
                @dragleave.prevent="handleDragLeave"
                @drop.prevent="handleDrop"
                @click="triggerFileInput"
              >
                <input
                  ref="fileInput"
                  type="file"
                  multiple
                  accept=".pdf,.md,.txt"
                  @change="handleFileSelect"
                  style="display: none"
                  :disabled="loading"
                />
                
                <div v-if="files.length === 0" class="upload-placeholder">
                  <div class="upload-icon">↑</div>
                  <div class="upload-title">ファイルをドラッグ＆ドロップ</div>
                  <div class="upload-hint">またはクリックして選択</div>
                </div>
                
                <div v-else class="file-list">
                  <div v-for="(file, index) in files" :key="index" class="file-item">
                    <span class="file-icon">📄</span>
                    <span class="file-name">{{ file.name }}</span>
                    <button @click.stop="removeFile(index)" class="remove-btn">×</button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Divider -->
            <div class="console-divider">
              <span>入力パラメータ</span>
            </div>

            <!-- Input area -->
            <div class="console-section">
              <div class="console-header">
                <span class="console-label">>_ 02 / キャリア目標</span>
              </div>
              <div class="input-wrapper">
                <textarea
                  v-model="formData.simulationRequirement"
                  class="code-input"
                  placeholder="// キャリアの目標や質問を記述してください（例: バックエンドエンジニアからプロダクトマネージャーへの転職を考えています...）"
                  rows="6"
                  :disabled="loading"
                ></textarea>
                <div class="model-badge">Engine: HR-Sim v1.0</div>
              </div>
            </div>

            <!-- Life context form -->
            <div class="console-divider">
              <span>ライフコンテキスト（任意）</span>
            </div>

            <div class="console-section">
              <div class="console-header">
                <span class="console-label">>_ 03 / 家族・資産情報</span>
                <span class="console-meta">ライフシミュレーション用</span>
              </div>
              
              <div class="life-context-form">
                <div class="form-row">
                  <label class="form-label">婚姻状況</label>
                  <select v-model="lifeContext.maritalStatus" class="form-select" :disabled="loading">
                    <option value="single">未婚</option>
                    <option value="married">既婚</option>
                    <option value="divorced">離婚</option>
                  </select>
                </div>
                
                <div class="form-row">
                  <label class="form-label">子供</label>
                  <div class="children-inputs">
                    <div v-for="(child, idx) in lifeContext.children" :key="idx" class="child-entry">
                      <input type="number" v-model.number="child.age" min="0" max="30" 
                        class="form-input-small" placeholder="年齢" :disabled="loading" />
                      <span class="form-unit">歳</span>
                      <button @click="removeChild(idx)" class="remove-btn-small" :disabled="loading">×</button>
                    </div>
                    <button @click="addChild" class="add-btn-small" :disabled="loading">+ 子供を追加</button>
                  </div>
                </div>
                
                <div class="form-row">
                  <label class="form-label">親の年齢</label>
                  <div class="parent-inputs">
                    <input type="number" v-model.number="lifeContext.parentAge1" min="40" max="100"
                      class="form-input-small" placeholder="父" :disabled="loading" />
                    <input type="number" v-model.number="lifeContext.parentAge2" min="40" max="100"
                      class="form-input-small" placeholder="母" :disabled="loading" />
                  </div>
                </div>
                
                <div class="form-row">
                  <label class="form-label">住宅ローン残額</label>
                  <input type="number" v-model.number="lifeContext.mortgageRemaining" min="0" step="100"
                    class="form-input" placeholder="0" :disabled="loading" />
                  <span class="form-unit">万円</span>
                </div>
                
                <div class="form-row">
                  <label class="form-label">金融資産</label>
                  <select v-model="lifeContext.cashBufferRange" class="form-select" :disabled="loading">
                    <option value="500未満">500万円未満</option>
                    <option value="500-2000">500〜2000万円</option>
                    <option value="2000+">2000万円以上</option>
                  </select>
                </div>
              </div>
            </div>

            <!-- Start button -->
            <div class="console-section btn-section">
              <button 
                class="start-engine-btn"
                @click="startSimulation"
                :disabled="!canSubmit || loading"
              >
                <span v-if="!loading">キャリア分析を開始</span>
                <span v-else>分析中...</span>
                <span class="btn-arrow">→</span>
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- Historical project database -->
      <HistoryDatabase />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import HistoryDatabase from '../components/HistoryDatabase.vue'

const router = useRouter()

// Form data
const formData = ref({
  simulationRequirement: ''
})

// Life context form data
const lifeContext = reactive({
  maritalStatus: 'single',
  children: [],
  parentAge1: null,
  parentAge2: null,
  mortgageRemaining: 0,
  cashBufferRange: '500未満',
})

// Child management
const addChild = () => {
  lifeContext.children.push({ age: 0 })
}
const removeChild = (idx) => {
  lifeContext.children.splice(idx, 1)
}

// File list
const files = ref([])

// State
const loading = ref(false)
const error = ref('')
const isDragOver = ref(false)

// File input ref
const fileInput = ref(null)

// Computed: can submit
const canSubmit = computed(() => {
  return formData.value.simulationRequirement.trim() !== '' && files.value.length > 0
})

// Trigger file selection
const triggerFileInput = () => {
  if (!loading.value) {
    fileInput.value?.click()
  }
}

// Handle file selection
const handleFileSelect = (event) => {
  const selectedFiles = Array.from(event.target.files)
  addFiles(selectedFiles)
}

// Handle drag events
const handleDragOver = (e) => {
  if (!loading.value) {
    isDragOver.value = true
  }
}

const handleDragLeave = (e) => {
  isDragOver.value = false
}

const handleDrop = (e) => {
  isDragOver.value = false
  if (loading.value) return
  
  const droppedFiles = Array.from(e.dataTransfer.files)
  addFiles(droppedFiles)
}

// Add files
const addFiles = (newFiles) => {
  const validFiles = newFiles.filter(file => {
    const ext = file.name.split('.').pop().toLowerCase()
    return ['pdf', 'md', 'txt'].includes(ext)
  })
  files.value.push(...validFiles)
}

// Remove file
const removeFile = (index) => {
  files.value.splice(index, 1)
}

// Scroll to bottom
const scrollToBottom = () => {
  window.scrollTo({
    top: document.body.scrollHeight,
    behavior: 'smooth'
  })
}

// Run Simulation - navigate immediately, API calls happen on Process page
const startSimulation = () => {
  if (!canSubmit.value || loading.value) return
  
  // Store pending upload data
  import('../store/pendingUpload.js').then(({ setPendingUpload }) => {
    // Build lifeContext payload
    const lifeCtx = {
      marital_status: lifeContext.maritalStatus,
      children: lifeContext.children.map(c => ({ relation: 'child', age: c.age })),
      parents: [],
      mortgage_remaining: lifeContext.mortgageRemaining || 0,
      cash_buffer_range: lifeContext.cashBufferRange,
    }
    if (lifeContext.parentAge1) lifeCtx.parents.push({ relation: 'parent', age: lifeContext.parentAge1 })
    if (lifeContext.parentAge2) lifeCtx.parents.push({ relation: 'parent', age: lifeContext.parentAge2 })
    
    setPendingUpload(files.value, formData.value.simulationRequirement, lifeCtx)
    
    // Navigate to Process page immediately (using special ID for new project)
    router.push({
      name: 'Process',
      params: { projectId: 'new' }
    })
  })
}
</script>

<style scoped>
/* Global variables and reset */
:root {
  --black: #000000;
  --white: #FFFFFF;
  --orange: #FF4500;
  --gray-light: #F5F5F5;
  --gray-text: #666666;
  --border: #E5E5E5;
  /* 
    Space Grotesk for titles, JetBrains Mono for code/labels
    Ensure these Google Fonts are imported in index.html
  */
  --font-mono: 'JetBrains Mono', monospace;
  --font-sans: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  --font-cn: 'Noto Sans SC', system-ui, sans-serif;
}

.home-container {
  min-height: 100vh;
  background: var(--white);
  font-family: var(--font-sans);
  color: var(--black);
}

/* Top navigation */
.navbar {
  height: 60px;
  background: var(--black);
  color: var(--white);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 40px;
}

.nav-brand {
  font-family: var(--font-mono);
  font-weight: 800;
  letter-spacing: 1px;
  font-size: 1.2rem;
}

.nav-links {
  display: flex;
  align-items: center;
}

.github-link {
  color: var(--white);
  text-decoration: none;
  font-family: var(--font-mono);
  font-size: 0.9rem;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: opacity 0.2s;
}

.github-link:hover {
  opacity: 0.8;
}

.arrow {
  font-family: sans-serif;
}

/* Main content area */
.main-content {
  max-width: 1400px;
  margin: 0 auto;
  padding: 60px 40px;
}

/* Hero area */
.hero-section {
  display: flex;
  justify-content: space-between;
  margin-bottom: 80px;
  position: relative;
}

.hero-left {
  flex: 1;
  padding-right: 60px;
}

.tag-row {
  display: flex;
  align-items: center;
  gap: 15px;
  margin-bottom: 25px;
  font-family: var(--font-mono);
  font-size: 0.8rem;
}

.orange-tag {
  background: var(--orange);
  color: var(--white);
  padding: 4px 10px;
  font-weight: 700;
  letter-spacing: 1px;
  font-size: 0.75rem;
}

.version-text {
  color: #999;
  font-weight: 500;
  letter-spacing: 0.5px;
}

.main-title {
  font-size: 4.5rem;
  line-height: 1.2;
  font-weight: 500;
  margin: 0 0 40px 0;
  letter-spacing: -2px;
  color: var(--black);
}

.gradient-text {
  background: linear-gradient(90deg, #000000 0%, #444444 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  display: inline-block;
}

.hero-desc {
  font-size: 1.05rem;
  line-height: 1.8;
  color: var(--gray-text);
  max-width: 640px;
  margin-bottom: 50px;
  font-weight: 400;
  text-align: justify;
}

.hero-desc p {
  margin-bottom: 1.5rem;
}

.highlight-bold {
  color: var(--black);
  font-weight: 700;
}

.highlight-orange {
  color: var(--orange);
  font-weight: 700;
  font-family: var(--font-mono);
}

.highlight-code {
  background: rgba(0, 0, 0, 0.05);
  padding: 2px 6px;
  border-radius: 2px;
  font-family: var(--font-mono);
  font-size: 0.9em;
  color: var(--black);
  font-weight: 600;
}

.slogan-text {
  font-size: 1.2rem;
  font-weight: 520;
  color: var(--black);
  letter-spacing: 1px;
  border-left: 3px solid var(--orange);
  padding-left: 15px;
  margin-top: 20px;
}

.blinking-cursor {
  color: var(--orange);
  animation: blink 1s step-end infinite;
  font-weight: 700;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.decoration-square {
  width: 16px;
  height: 16px;
  background: var(--orange);
}

.hero-right {
  flex: 0.8;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: flex-end;
}

.logo-container {
  width: 100%;
  display: flex;
  justify-content: flex-end;
  padding-right: 40px;
}

.hero-logo {
  max-width: 500px; /* Adjust logo size */
  width: 100%;
}

.scroll-down-btn {
  width: 40px;
  height: 40px;
  border: 1px solid var(--border);
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--orange);
  font-size: 1.2rem;
  transition: all 0.2s;
}

.scroll-down-btn:hover {
  border-color: var(--orange);
}

/* Dashboard dual-column layout */
.dashboard-section {
  display: flex;
  gap: 60px;
  border-top: 1px solid var(--border);
  padding-top: 60px;
  align-items: flex-start;
}

.dashboard-section .left-panel,
.dashboard-section .right-panel {
  display: flex;
  flex-direction: column;
}

/* Left panel */
.left-panel {
  flex: 0.8;
}

.panel-header {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: #999;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 20px;
}

.status-dot {
  color: var(--orange);
  font-size: 0.8rem;
}

.section-title {
  font-size: 2rem;
  font-weight: 520;
  margin: 0 0 15px 0;
}

.section-desc {
  color: var(--gray-text);
  margin-bottom: 25px;
  line-height: 1.6;
}

.metrics-row {
  display: flex;
  gap: 20px;
  margin-bottom: 15px;
}

.metric-card {
  border: 1px solid var(--border);
  padding: 20px 30px;
  min-width: 150px;
}

.metric-value {
  font-family: var(--font-mono);
  font-size: 1.8rem;
  font-weight: 520;
  margin-bottom: 5px;
}

.metric-label {
  font-size: 0.85rem;
  color: #999;
}

/* Project simulation steps intro */
.steps-container {
  border: 1px solid var(--border);
  padding: 30px;
  position: relative;
}

.steps-header {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: #999;
  margin-bottom: 25px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.diamond-icon {
  font-size: 1.2rem;
  line-height: 1;
}

.workflow-list {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.workflow-item {
  display: flex;
  align-items: flex-start;
  gap: 20px;
}

.step-num {
  font-family: var(--font-mono);
  font-weight: 700;
  color: var(--black);
  opacity: 0.3;
}

.step-info {
  flex: 1;
}

.step-title {
  font-weight: 520;
  font-size: 1rem;
  margin-bottom: 4px;
}

.step-desc {
  font-size: 0.85rem;
  color: var(--gray-text);
}

/* Right interactive console */
.right-panel {
  flex: 1.2;
}

.console-box {
  border: 1px solid #CCC; /* Outer solid border */
  padding: 8px; /* Inner padding creates double border effect */
}

.console-section {
  padding: 20px;
}

.console-section.btn-section {
  padding-top: 0;
}

.console-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 15px;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: #666;
}

.upload-zone {
  border: 1px dashed #CCC;
  height: 200px;
  overflow-y: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.3s;
  background: #FAFAFA;
}

.upload-zone.has-files {
  align-items: flex-start;
}

.upload-zone:hover {
  background: #F0F0F0;
  border-color: #999;
}

.upload-placeholder {
  text-align: center;
}

.upload-icon {
  width: 40px;
  height: 40px;
  border: 1px solid #DDD;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 15px;
  color: #999;
}

.upload-title {
  font-weight: 500;
  font-size: 0.9rem;
  margin-bottom: 5px;
}

.upload-hint {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: #999;
}

.file-list {
  width: 100%;
  padding: 15px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.file-item {
  display: flex;
  align-items: center;
  background: var(--white);
  padding: 8px 12px;
  border: 1px solid #EEE;
  font-family: var(--font-mono);
  font-size: 0.85rem;
}

.file-name {
  flex: 1;
  margin: 0 10px;
}

.remove-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1.2rem;
  color: #999;
}

.console-divider {
  display: flex;
  align-items: center;
  margin: 10px 0;
}

.console-divider::before,
.console-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: #EEE;
}

.console-divider span {
  padding: 0 15px;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: #BBB;
  letter-spacing: 1px;
}

.input-wrapper {
  position: relative;
  border: 1px solid #DDD;
  background: #FAFAFA;
}

.code-input {
  width: 100%;
  border: none;
  background: transparent;
  padding: 20px;
  font-family: var(--font-mono);
  font-size: 0.9rem;
  line-height: 1.6;
  resize: vertical;
  outline: none;
  min-height: 150px;
}

.model-badge {
  position: absolute;
  bottom: 10px;
  right: 15px;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: #AAA;
}

.start-engine-btn {
  width: 100%;
  background: var(--black);
  color: var(--white);
  border: none;
  padding: 20px;
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 1.1rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  transition: all 0.3s ease;
  letter-spacing: 1px;
  position: relative;
  overflow: hidden;
}

/* Clickable state (non-disabled) */
.start-engine-btn:not(:disabled) {
  background: var(--black);
  border: 1px solid var(--black);
  animation: pulse-border 2s infinite;
}

.start-engine-btn:hover:not(:disabled) {
  background: var(--orange);
  border-color: var(--orange);
  transform: translateY(-2px);
}

.start-engine-btn:active:not(:disabled) {
  transform: translateY(0);
}

.start-engine-btn:disabled {
  background: #E5E5E5;
  color: #999;
  cursor: not-allowed;
  transform: none;
  border: 1px solid #E5E5E5;
}

/* Guide animation: subtle border pulse */
@keyframes pulse-border {
  0% { box-shadow: 0 0 0 0 rgba(0, 0, 0, 0.2); }
  70% { box-shadow: 0 0 0 6px rgba(0, 0, 0, 0); }
  100% { box-shadow: 0 0 0 0 rgba(0, 0, 0, 0); }
}

/* Responsive layout */
@media (max-width: 1024px) {
  .dashboard-section {
    flex-direction: column;
  }
  
  .hero-section {
    flex-direction: column;
  }
  
  .hero-left {
    padding-right: 0;
    margin-bottom: 40px;
  }
  
  .hero-logo {
    max-width: 200px;
    margin-bottom: 20px;
  }
}

/* Life context form */
.life-context-form {
  padding: 15px 20px;
}

.form-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.form-label {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: #888;
  min-width: 100px;
  flex-shrink: 0;
}

.form-select, .form-input {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  background: #1a1a1a;
  border: 1px solid #333;
  color: #eee;
  padding: 6px 10px;
  border-radius: 4px;
  flex: 1;
  max-width: 200px;
}

.form-select:focus, .form-input:focus {
  border-color: #ff6600;
  outline: none;
}

.form-input-small {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  background: #1a1a1a;
  border: 1px solid #333;
  color: #eee;
  padding: 6px 10px;
  border-radius: 4px;
  width: 70px;
}

.form-unit {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: #666;
}

.children-inputs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.child-entry {
  display: flex;
  align-items: center;
  gap: 4px;
}

.parent-inputs {
  display: flex;
  gap: 10px;
}

.add-btn-small {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  background: transparent;
  border: 1px dashed #555;
  color: #888;
  padding: 4px 12px;
  border-radius: 4px;
  cursor: pointer;
}

.add-btn-small:hover {
  border-color: #ff6600;
  color: #ff6600;
}

.remove-btn-small {
  background: transparent;
  border: none;
  color: #666;
  cursor: pointer;
  font-size: 1rem;
  padding: 0 4px;
}

.remove-btn-small:hover {
  color: #ff4444;
}
</style>
