import { ALL_ENTITY_TYPES } from '@/constants/entityTypes'

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
        {ALL_TYPES.map((type) => (
          <label key={type} className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={selectedSet.has(type)}
              onChange={() => toggle(type)}
              className="size-4 rounded"
            />
            {type}
          </label>
        ))}
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => onChange([...ALL_TYPES])}
          className="flex-1 rounded border px-2 py-1 text-xs"
        >
          Select all
        </button>
        <button
          onClick={() => onChange([])}
          className="flex-1 rounded border px-2 py-1 text-xs"
        >
          Clear all
        </button>
      </div>

      <div className="text-xs text-muted-foreground">
        {nodeCount} nodes, {edgeCount} edges
      </div>
    </div>
  )
}
