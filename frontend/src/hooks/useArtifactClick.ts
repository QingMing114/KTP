import { useState } from 'react'
import { getApiKey, getJwtToken } from '../services/api'

interface ArtifactError {
  message: string
}

export function useArtifactClick() {
  const [artifactError, setArtifactError] = useState<ArtifactError | null>(null)

  async function handleArtifactClick(href: string) {
    setArtifactError(null)
    try {
      const headers: Record<string, string> = {}
      const jwt = getJwtToken()
      const apiKey = getApiKey()
      if (jwt) {
        headers["Authorization"] = `Bearer ${jwt}`
      } else if (apiKey) {
        headers["Authorization"] = `Bearer ${apiKey}`
      }
      const res = await fetch(href, { method: "HEAD", headers })
      if (res.ok || res.status === 200) {
        window.open(href, "_blank", "noreferrer")
      } else if (res.status === 404 || res.status === 403) {
        const getRes = await fetch(href, { method: "GET", headers })
        const data = await getRes.json().catch(() => null)
        const detail = data?.detail || getRes.statusText
        if (detail === "artifact_not_found") {
          setArtifactError({ message: "文件不存在或已被清理，无法打开此产物" })
        } else if (detail === "artifact_path_not_allowed") {
          setArtifactError({ message: "文件路径不在允许范围内" })
        } else if (detail === "artifact_suffix_not_allowed") {
          setArtifactError({ message: "不支持的文件类型" })
        } else {
          setArtifactError({ message: `无法打开产物：${detail}` })
        }
      } else {
        window.open(href, "_blank", "noreferrer")
      }
    } catch {
      window.open(href, "_blank", "noreferrer")
    }
  }

  function clearArtifactError() {
    setArtifactError(null)
  }

  return { artifactError, handleArtifactClick, clearArtifactError }
}
