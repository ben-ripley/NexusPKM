import { useState } from 'react'
import { cn } from '@/lib/utils'
import ProviderSettings from '@/components/settings/ProviderSettings'
import ConnectorSettings from '@/components/settings/ConnectorSettings'
import PreferenceSettings from '@/components/settings/PreferenceSettings'

type Tab = 'providers' | 'connectors' | 'preferences'

const TABS: { id: Tab; label: string }[] = [
  { id: 'providers', label: 'Providers' },
  { id: 'connectors', label: 'Connectors' },
  { id: 'preferences', label: 'Preferences' },
]

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>('providers')

  return (
    <div className="flex flex-col gap-6 p-6">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <div className="flex gap-1 border-b">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              'px-4 py-2 text-sm font-medium transition-colors',
              activeTab === tab.id
                ? 'border-b-2 border-primary text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="max-w-2xl">
        {activeTab === 'providers' && <ProviderSettings />}
        {activeTab === 'connectors' && <ConnectorSettings />}
        {activeTab === 'preferences' && <PreferenceSettings />}
      </div>
    </div>
  )
}
