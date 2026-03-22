import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { useNotificationPreferences, useUpdatePreferences } from '@/hooks/useNotifications'
import type { NotificationPreferences } from '@/services/api'

export default function NotificationSettings() {
  const { data: prefs, isLoading, error } = useNotificationPreferences()
  const { mutate: savePrefs, isPending } = useUpdatePreferences()
  // Local edits override the server value; falls back to fetched prefs before first edit.
  const [localForm, setLocalForm] = useState<NotificationPreferences | null>(null)
  const form = localForm ?? prefs ?? null

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading notification settings…</p>
  }

  if (error) {
    return <p className="text-sm text-destructive">Failed to load notification preferences.</p>
  }

  if (!form) return null

  function toggle(field: keyof NotificationPreferences) {
    if (!form) return
    setLocalForm({ ...form, [field]: !form[field] })
  }

  function handleSave() {
    if (!form) return
    savePrefs(form)
  }

  return (
    <div className="flex flex-col gap-4">
      <h3 className="text-sm font-semibold">Notifications</h3>

      <div className="flex flex-col gap-3">
        <label className="flex items-center gap-2">
          <Checkbox
            id="meeting-prep"
            aria-label="Meeting prep notifications"
            checked={form.meeting_prep_enabled}
            onCheckedChange={() => toggle('meeting_prep_enabled')}
          />
          <span className="text-sm">Meeting prep notifications</span>
        </label>

        {form.meeting_prep_enabled && (
          <div className="ml-6 flex items-center gap-2">
            <label htmlFor="lead-time" className="text-xs text-muted-foreground">
              Lead time (minutes)
            </label>
            <Input
              id="lead-time"
              type="number"
              className="h-7 w-24 text-xs"
              value={form.meeting_prep_lead_time_minutes}
              onChange={(e) =>
                setLocalForm({ ...form, meeting_prep_lead_time_minutes: Number(e.target.value) })
              }
            />
          </div>
        )}

        <label className="flex items-center gap-2">
          <Checkbox
            id="related-content"
            aria-label="Related content alerts"
            checked={form.related_content_enabled}
            onCheckedChange={() => toggle('related_content_enabled')}
          />
          <span className="text-sm">Related content alerts</span>
        </label>

        <label className="flex items-center gap-2">
          <Checkbox
            id="contradictions"
            aria-label="Contradiction alerts"
            checked={form.contradiction_alerts_enabled}
            onCheckedChange={() => toggle('contradiction_alerts_enabled')}
          />
          <span className="text-sm">Contradiction alerts</span>
        </label>

        <div className="flex flex-col gap-1">
          <label htmlFor="webhook-url" className="text-xs text-muted-foreground">
            Webhook URL (optional)
          </label>
          <Input
            id="webhook-url"
            type="url"
            placeholder="https://example.com/hook"
            className="h-8 text-xs"
            value={form.webhook_url ?? ''}
            onChange={(e) =>
              setLocalForm({ ...form, webhook_url: e.target.value || null })
            }
          />
        </div>
      </div>

      <Button
        size="sm"
        onClick={handleSave}
        disabled={isPending}
        className="w-fit"
      >
        {isPending ? 'Saving…' : 'Save'}
      </Button>
    </div>
  )
}
