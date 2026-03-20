import { Link } from 'react-router-dom'
import { CircleAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function NotFoundPage() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 text-muted-foreground">
      <CircleAlert className="size-12" />
      <h1 className="text-2xl font-semibold">Page Not Found</h1>
      <p>The page you're looking for doesn't exist.</p>
      <Button render={<Link to="/" />} nativeButton={false}>
        Go to Dashboard
      </Button>
    </div>
  )
}
