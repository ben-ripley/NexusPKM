import { Popover as PopoverPrimitive } from '@base-ui/react/popover'
import { cn } from '@/lib/utils'

const PopoverRoot = PopoverPrimitive.Root
const PopoverTrigger = PopoverPrimitive.Trigger

function PopoverContent({
  className,
  align = 'start',
  side = 'bottom',
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Popup> & {
  align?: 'start' | 'center' | 'end'
  side?: 'top' | 'bottom' | 'left' | 'right'
}) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Positioner align={align} side={side} sideOffset={6}>
        <PopoverPrimitive.Popup
          className={cn(
            'z-50 rounded-md border bg-popover p-0 text-popover-foreground shadow-md outline-none',
            'data-[starting-style]:animate-in data-[ending-style]:animate-out',
            'data-[starting-style]:fade-in-0 data-[ending-style]:fade-out-0',
            'data-[starting-style]:zoom-in-95 data-[ending-style]:zoom-out-95',
            className,
          )}
          {...props}
        />
      </PopoverPrimitive.Positioner>
    </PopoverPrimitive.Portal>
  )
}

export { PopoverRoot, PopoverTrigger, PopoverContent }
