import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import ProviderSettings from '@/components/settings/ProviderSettings'
import ConnectorSettings from '@/components/settings/ConnectorSettings'
import PreferenceSettings from '@/components/settings/PreferenceSettings'
import NotificationSettings from '@/components/settings/NotificationSettings'

export default function SettingsPage() {
  return (
    <div className="flex flex-col gap-6 p-6">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <Tabs defaultValue="providers" className="max-w-2xl">
        <TabsList variant="line">
          <TabsTrigger value="providers">Providers</TabsTrigger>
          <TabsTrigger value="connectors">Connectors</TabsTrigger>
          <TabsTrigger value="preferences">Preferences</TabsTrigger>
          <TabsTrigger value="notifications">Notifications</TabsTrigger>
        </TabsList>

        <TabsContent value="providers" className="pt-6">
          <ProviderSettings />
        </TabsContent>
        <TabsContent value="connectors" className="pt-6">
          <ConnectorSettings />
        </TabsContent>
        <TabsContent value="preferences" className="pt-6">
          <PreferenceSettings />
        </TabsContent>
        <TabsContent value="notifications" className="pt-6">
          <NotificationSettings />
        </TabsContent>
      </Tabs>
    </div>
  )
}
