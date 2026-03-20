import { useRouteError, isRouteErrorResponse, Link } from 'react-router-dom'
import { CircleAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function ErrorFallback() {
  const error = useRouteError()

  const message = isRouteErrorResponse(error)
    ? `${error.status}: ${error.statusText}`
    : error instanceof Error
      ? error.message
      : 'An unexpected error occurred'

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 text-muted-foreground">
      <CircleAlert className="size-12 text-destructive" />
      <h1 className="text-2xl font-semibold text-foreground">Something went wrong</h1>
      <p>{message}</p>
      <Button render={<Link to="/" />} nativeButton={false}>
        Go to Dashboard
      </Button>
    </div>
  )
}
