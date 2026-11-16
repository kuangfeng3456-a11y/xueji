/** 语音输入：云端已开通时录音上传，否则由调用方改用本机识别或文字。 */

export async function cloudSpeechReady(api) {
  try {
    const data = await api.cloudServices()
    const sis = (data.items || []).find((item) => item.key === 'sis')
    return Boolean(sis && sis.status === 'ok')
  } catch (e) {
    return false
  }
}

export function canRecord() {
  return Boolean(
    typeof window !== 'undefined' &&
      window.MediaRecorder &&
      navigator.mediaDevices &&
      navigator.mediaDevices.getUserMedia
  )
}

export async function startRecorder() {
  if (!canRecord()) {
    throw new Error('当前环境不能录音')
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  const mime = window.MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : ''
  const recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream)
  const chunks = []
  recorder.ondataavailable = (event) => {
    if (event.data && event.data.size) chunks.push(event.data)
  }
  return {
    start() {
      recorder.start()
    },
    stop() {
      return new Promise((resolve) => {
        recorder.onstop = () => {
          stream.getTracks().forEach((track) => track.stop())
          const type = recorder.mimeType || 'audio/webm'
          resolve(new Blob(chunks, { type }))
        }
        if (recorder.state === 'inactive') {
          stream.getTracks().forEach((track) => track.stop())
          resolve(new Blob(chunks, { type: recorder.mimeType || 'audio/webm' }))
          return
        }
        recorder.stop()
      })
    }
  }
}
