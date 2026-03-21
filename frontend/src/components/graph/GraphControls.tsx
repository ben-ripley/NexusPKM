import { Checkbox } from '@/components/ui/checkbox'
import { Button } from '@/components/ui/button'
import { ALL_ENTITY_TYPES, ENTITY_TYPE_COLORS } from '@/constants/entityTypes'
import { formatSourceType } from '@/lib/utils'

const ALL_TYPES = ALL_ENTITY_TYPES

interface Props {
  selectedTypes: string[]
  onChange: (types: string[]) => void
  nodeCount: number
  edgeCount: number
}

export default function GraphControls({ selectedTypes, onChange, nodeCount, edgeCount }: Props) {
  const selectedSet = new Set(selectedTypes)

  function toggle(type: string) {
    if (selectedSet.has(type)) {
      onChange(selectedTypes.filter((t) => t !== type))
    } else {
      onChange([...selectedTypes, type])
    }
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="text-sm font-semibold">Filters</div>

      <div className="flex flex-col gap-2">
        {ALL_TYPES.map((type) => {
          const color = ENTITY_TYPE_COLORS[type] ?? '#94a3b8'
          return (
            <label key={type} className="flex cursor-pointer items-center gap-2 text-sm">
              <Checkbox
                checked={selectedSet.has(type)}
                onCheckedChange={() => toggle(type)}
                aria-label={formatSourceType(type)}
              />
              <span
                className="rounded-full px-2.5 py-0.5 text-xs font-semibold"
                style={{
                  backgroundColor: `${color}26`,
                  color,
                  border: `1px solid ${color}66`,
                }}
              >
                {formatSourceType(type)}
              </span>
            </label>
          )
        })}
      </div>

      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onChange([...ALL_TYPES])}
          className="flex-1 text-xs"
        >
          Select all
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onChange([])}
          className="flex-1 text-xs"
        >
          Clear all
        </Button>
      </div>

      <div className="text-xs text-muted-foreground">
        {nodeCount} nodes, {edgeCount} edges
      </div>
    </div>
  )
}
