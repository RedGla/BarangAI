import { Dialog } from 'radix-ui'
import { X } from 'lucide-react'
import { Txt, useText } from '../../lib/i18n'

/**
 * Full-screen view of the report photo over a blurred page. Only ever given the server's face- and plate-blurred
 * copy: callers open it once that copy is ready, never the original.
 */
export function PhotoViewer({
  src,
  open,
  onOpenChange,
}: {
  src: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const t = useText()
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="photo-viewer-backdrop fixed inset-0 z-50 bg-black/55 backdrop-blur-xl" />
        <Dialog.Content
          aria-describedby={undefined}
          className="photo-viewer fixed inset-0 z-50 flex items-center justify-center p-4 pt-[max(4.5rem,calc(env(safe-area-inset-top)+4rem))] pb-[max(1.5rem,env(safe-area-inset-bottom))] outline-none"
          onClick={event => {
            // A tap on the blurred space around the photo closes it, as on a phone's gallery.
            if (event.target === event.currentTarget) onOpenChange(false)
          }}
        >
          <Dialog.Title className="sr-only">
            <Txt>Report photo</Txt>
          </Dialog.Title>
          <img
            src={src}
            alt={t('Preview of incident photo')}
            className="max-h-full max-w-full rounded-2xl object-contain shadow-2xl select-none"
            draggable={false}
          />
          <Dialog.Close
            className="absolute top-[max(1rem,env(safe-area-inset-top))] right-4 grid size-12 place-items-center rounded-full border-2 border-b-4 border-white/30 bg-black/45 text-white transition-transform active:translate-y-0.5 active:border-b-2 focus-visible:ring-2 focus-visible:ring-white focus-visible:outline-none"
            aria-label={t('Close photo')}
          >
            <X className="size-6" strokeWidth={3} aria-hidden="true" />
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
