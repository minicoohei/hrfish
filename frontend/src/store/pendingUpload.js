/**
 * Temporary storage for pending upload files and requirements
 * Navigate immediately after clicking start on homepage, API calls happen on Process page
 */
import { reactive } from 'vue'

const state = reactive({
  files: [],
  simulationRequirement: '',
  lifeContext: null,  // ライフシミュレーション用フォームデータ
  isPending: false
})

export function setPendingUpload(files, requirement, lifeContext = null) {
  state.files = files
  state.simulationRequirement = requirement
  state.lifeContext = lifeContext
  state.isPending = true
}

export function getPendingUpload() {
  return {
    files: state.files,
    simulationRequirement: state.simulationRequirement,
    lifeContext: state.lifeContext,
    isPending: state.isPending
  }
}

export function clearPendingUpload() {
  state.files = []
  state.simulationRequirement = ''
  state.lifeContext = null
  state.isPending = false
}

export default state
