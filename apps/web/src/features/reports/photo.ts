/** Photo preparation in the browser: read what the server needs from the original, then shrink it for upload. */

/** Longest side after shrinking; the API applies the same cap (MAX_IMAGE_EDGE). */
const MAX_EDGE = 1600
/** Phones save 5–20 MB photos; anything this size is shrunk before the 5 MB upload limit applies. */
export const MAX_ORIGINAL_BYTES = 25_000_000
export const MAX_UPLOAD_BYTES = 5_000_000

/** Capture time and camera from the original file. Shrinking drops them, so the form sends them alongside. */
export type PhotoDetails = { takenAt: string | null; camera: boolean }

export async function photoDetails(file: File): Promise<PhotoDetails> {
  try {
    const { default: exifr } = await import('exifr')
    // reviveValues: false keeps the raw "YYYY:MM:DD HH:MM:SS" camera time, which the API reads as Philippine time.
    const tags = await exifr.parse(file, { pick: ['DateTimeOriginal', 'Make', 'Model'], reviveValues: false })
    const taken = typeof tags?.DateTimeOriginal === 'string' ? tags.DateTimeOriginal : null
    return { takenAt: taken, camera: Boolean(tags?.Make || tags?.Model) }
  } catch {
    return { takenAt: null, camera: false }
  }
}

/**
 * A JPEG at most 1600 px on the long side, so uploads are quick on mobile data and fit the 5 MB limit.
 * Returns the original when the browser cannot decode it or shrinking would not help.
 */
export async function shrinkPhoto(file: File): Promise<File> {
  if (typeof createImageBitmap !== 'function') return file
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
    const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height))
    if (scale === 1 && file.size <= 1_500_000) {
      bitmap.close()
      return file
    }
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(bitmap.width * scale)
    canvas.height = Math.round(bitmap.height * scale)
    canvas.getContext('2d')?.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    bitmap.close()
    const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.82))
    if (!blob || blob.size >= file.size) return file
    return new File([blob], `${file.name.replace(/\.[^.]+$/, '') || 'photo'}.jpg`, { type: 'image/jpeg' })
  } catch {
    return file
  }
}
