// Screen capture. The old client clamped width and height independently (distorting non-16:9 screens) and
// used JPEG quality 0.6, which smeared code. This keeps the aspect ratio and sends crisper frames.
const MAX_W = 1280
const MAX_H = 720

export async function startScreen({ onFrame, onEnded, intervalMs = 2000 }) {
  const stream = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: 5 }, audio: false })
  const video = document.createElement('video')
  video.srcObject = stream
  video.muted = true
  await video.play()
  await new Promise((r) => setTimeout(r, 400))
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')

  const grab = () => {
    if (!video.videoWidth) return
    const scale = Math.min(1, MAX_W / video.videoWidth, MAX_H / video.videoHeight)
    canvas.width = Math.round(video.videoWidth * scale)
    canvas.height = Math.round(video.videoHeight * scale)
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
    canvas.toBlob(async (blob) => { if (blob) onFrame(await blob.arrayBuffer()) }, 'image/jpeg', 0.85)
  }
  const timer = setInterval(grab, intervalMs)
  const track = stream.getVideoTracks()[0]
  track.onended = () => { clearInterval(timer); onEnded?.() }
  grab()
  return { stop() { clearInterval(timer); stream.getTracks().forEach((t) => t.stop()) } }
}
