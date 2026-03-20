import { useRouteError, isRouteErrorResponse, Link } from 'react-router-dom'
import { CircleAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { log } from '@/lib/log'

export function ErrorFallback() {
  const error = useRouteError()

  log.error('route error', error)

  const userMessage = isRouteErrorResponse(error)
    ? `${error.status}: ${error.statusText}`
    : 'An unexpected error occurred. Please try again.'

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 text-muted-foreground">
      <CircleAlert className="size-12 text-destructive" />
      <h1 className="text-2xl font-semibold text-foreground">Something went wrong</h1>
      <p>{userMessage}</p>
      {import.meta.env.DEV && error instanceof Error && (
        <pre className="max-w-lg overflow-auto rounded-md bg-muted p-4 text-xs">
          {error.message}
        </pre>
      )}
      <Button render={<Link to="/" />} nativeButton={false}>
        Go to Dashboard
      </Button>
    </div>
  )
}
