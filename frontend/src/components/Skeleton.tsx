import React from 'react'

export const Skeleton: React.FC<{ className?: string }> = ({ className = '' }) => (
  <div className={`animate-pulse bg-stone-200 rounded ${className}`} />
)

export const PageSkeleton: React.FC = () => (
  <div className="p-6 space-y-4">
    <div className="flex items-center gap-3">
      <Skeleton className="w-6 h-6 rounded" />
      <Skeleton className="h-6 w-40" />
    </div>
    <div className="space-y-3">
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-4 w-1/2" />
    </div>
    <div className="grid grid-cols-3 gap-3">
      <Skeleton className="h-20 rounded-lg" />
      <Skeleton className="h-20 rounded-lg" />
      <Skeleton className="h-20 rounded-lg" />
    </div>
  </div>
)

export const CardSkeleton: React.FC = () => (
  <div className="bg-white rounded-xl border border-stone-200/60 p-4 space-y-3">
    <Skeleton className="h-4 w-2/3" />
    <Skeleton className="h-3 w-full" />
    <Skeleton className="h-3 w-4/5" />
  </div>
)

export const ListSkeleton: React.FC<{ count?: number }> = ({ count = 5 }) => (
  <div className="space-y-2">
    {Array.from({ length: count }).map((_, i) => (
      <div key={i} className="bg-white rounded-lg border border-stone-200/60 p-3 flex items-center gap-3">
        <Skeleton className="w-2 h-2 rounded-full shrink-0" />
        <Skeleton className="h-3 flex-1" />
        <Skeleton className="h-3 w-16" />
      </div>
    ))}
  </div>
)
