import { useEffect, useMemo, useState } from 'react'
import './App.css'

function App() {
  const [files, setFiles] = useState([])
  const [thumbResults, setThumbResults] = useState([])
  const [clusterResults, setClusterResults] = useState([])
  const [duplicateResults, setDuplicateResults] = useState([])
  const [isUploading, setIsUploading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [jobStatus, setJobStatus] = useState(null)
  const [clusterJob, setClusterJob] = useState(null)
  const [dedupeJob, setDedupeJob] = useState(null)
  const [isDragging, setIsDragging] = useState(false)

  const statusText = useMemo(() => {
    if (files.length === 0) {
      return {
        title: 'Waiting for photos',
        subtitle: 'Drag files into the canvas.',
      }
    }

    if (jobStatus && jobStatus.status !== 'completed') {
      const total = jobStatus.total || 0
      const completed = jobStatus.completed || 0
      return {
        title: 'Building thumbnails',
        subtitle: `Processed ${completed} of ${total} thumbnails.`,
      }
    }

    if (clusterJob && clusterJob.status !== 'completed') {
      const total = clusterJob.total || 0
      const completed = clusterJob.completed || 0
      return {
        title: 'Clustering events',
        subtitle: `Grouped ${completed} of ${total} photos.`,
      }
    }

    if (dedupeJob && dedupeJob.status !== 'completed') {
      const total = dedupeJob.total || 0
      const completed = dedupeJob.completed || 0
      return {
        title: 'Detecting duplicates',
        subtitle: `Checked ${completed} of ${total} thumbnails.`,
      }
    }

    return {
      title: `Loaded ${files.length} file${files.length === 1 ? '' : 's'}`,
      subtitle: isUploading
        ? 'Uploading originals and building thumbnails.'
        : 'Sources are staged locally for the next step.',
    }
  }, [files.length, isUploading, jobStatus, clusterJob, dedupeJob])

  function isPhotoFile(entry) {
    if (entry.file.type && entry.file.type.startsWith('image/')) {
      return true
    }

    const name = entry.file.name.toLowerCase()
    return [
      '.jpg',
      '.jpeg',
      '.png',
      '.gif',
      '.webp',
      '.heic',
      '.heif',
      '.tif',
      '.tiff',
      '.bmp',
    ].some((ext) => name.endsWith(ext))
  }

  async function readAllEntries(directoryReader) {
    const entries = []
    while (true) {
      const batch = await new Promise((resolve) => {
        directoryReader.readEntries(resolve)
      })
      if (!batch || batch.length === 0) {
        break
      }
      entries.push(...batch)
    }
    return entries
  }

  async function collectFilesFromEntry(entry) {
    if (entry.isFile) {
      const file = await new Promise((resolve) => entry.file(resolve))
      return file
        ? [
            {
              file,
              path: entry.fullPath || file.webkitRelativePath || file.name,
            },
          ]
        : []
    }

    if (entry.isDirectory) {
      const reader = entry.createReader()
      const entries = await readAllEntries(reader)
      const nested = await Promise.all(entries.map(collectFilesFromEntry))
      return nested.flat()
    }

    return []
  }

  async function collectFilesFromDataTransfer(dataTransfer) {
    const items = Array.from(dataTransfer?.items ?? [])
    if (items.length > 0) {
      const entryLists = await Promise.all(
        items
          .filter((item) => item.kind === 'file')
          .map((item) => (item.webkitGetAsEntry ? item.webkitGetAsEntry() : null))
          .filter(Boolean)
          .map(collectFilesFromEntry),
      )

      const filesFromEntries = entryLists.flat().filter(isPhotoFile)
      if (filesFromEntries.length > 0) {
        return filesFromEntries
      }
    }

    return Array.from(dataTransfer?.files ?? [])
      .map((file) => ({ file, path: file.webkitRelativePath || file.name }))
      .filter(isPhotoFile)
  }

  function handleDragOver(event) {
    event.preventDefault()
  }

  function handleDragEnter(event) {
    event.preventDefault()
    setIsDragging(true)
  }

  function handleDragLeave(event) {
    event.preventDefault()
    if (event.currentTarget.contains(event.relatedTarget)) {
      return
    }
    setIsDragging(false)
  }

  async function handleDrop(event) {
    event.preventDefault()
    setIsDragging(false)
    setErrorMessage('')
    const droppedFiles = await collectFilesFromDataTransfer(event.dataTransfer)
    if (droppedFiles.length === 0) {
      return
    }

    const nextFiles = []
    setFiles((prev) => {
      const existing = new Set(
        prev.map((entry) => `${entry.file.name}-${entry.file.lastModified}-${entry.path}`),
      )
      const next = [...prev]
      droppedFiles.forEach((entry) => {
        const key = `${entry.file.name}-${entry.file.lastModified}-${entry.path}`
        if (!existing.has(key)) {
          existing.add(key)
          next.push(entry)
          nextFiles.push(entry)
        }
      })
      return next
    })

    if (nextFiles.length === 0) {
      return
    }

    const formData = new FormData()
    nextFiles.forEach((entry) => {
      formData.append('files', entry.file, entry.file.name)
    })

    try {
      setIsUploading(true)
      const response = await fetch('/api/ingest', {
        method: 'POST',
        body: formData,
      })
      if (!response.ok) {
        throw new Error('Upload failed')
      }
      const data = await response.json()
      if (data.job_id) {
        setJobStatus({ id: data.job_id, status: 'queued', total: 0, completed: 0 })
      }
    } catch (error) {
      setErrorMessage('Unable to reach the thumbnail service. Is it running?')
    } finally {
      setIsUploading(false)
    }
  }

  async function triggerCluster() {
    try {
      setErrorMessage('')
      const response = await fetch('/api/cluster', { method: 'POST' })
      if (!response.ok) {
        throw new Error('Cluster job failed')
      }
      const data = await response.json()
      if (data.job_id) {
        setClusterJob({ id: data.job_id, status: 'queued', total: 0, completed: 0 })
      }
    } catch (error) {
      setErrorMessage('Unable to start clustering.')
    }
  }

  async function triggerDedupe() {
    try {
      setErrorMessage('')
      const response = await fetch('/api/dedupe', { method: 'POST' })
      if (!response.ok) {
        throw new Error('Dedupe job failed')
      }
      const data = await response.json()
      if (data.job_id) {
        setDedupeJob({ id: data.job_id, status: 'queued', total: 0, completed: 0 })
      }
    } catch (error) {
      setErrorMessage('Unable to start duplicate detection.')
    }
  }

  async function pollJob(jobId) {
    try {
      const response = await fetch(`/api/jobs/${jobId}`)
      if (!response.ok) {
        throw new Error('Job lookup failed')
      }
      const data = await response.json()
      setJobStatus(data)
      if (data.status === 'completed') {
        const thumbResponse = await fetch('/api/thumbnails')
        if (thumbResponse.ok) {
          const thumbData = await thumbResponse.json()
          setThumbResults(thumbData.items ?? [])
        }
      }
    } catch (error) {
      setErrorMessage('Unable to fetch thumbnail progress.')
    }
  }

  async function pollCluster(jobId) {
    try {
      const response = await fetch(`/api/jobs/${jobId}`)
      if (!response.ok) {
        throw new Error('Cluster lookup failed')
      }
      const data = await response.json()
      setClusterJob(data)
      if (data.status === 'completed') {
        const clusterResponse = await fetch('/api/clusters')
        if (clusterResponse.ok) {
          const clusterData = await clusterResponse.json()
          setClusterResults(clusterData.items ?? [])
        }
      }
    } catch (error) {
      setErrorMessage('Unable to fetch cluster progress.')
    }
  }

  async function pollDedupe(jobId) {
    try {
      const response = await fetch(`/api/jobs/${jobId}`)
      if (!response.ok) {
        throw new Error('Dedupe lookup failed')
      }
      const data = await response.json()
      setDedupeJob(data)
      if (data.status === 'completed') {
        const dedupeResponse = await fetch('/api/duplicates')
        if (dedupeResponse.ok) {
          const dedupeData = await dedupeResponse.json()
          setDuplicateResults(dedupeData.items ?? [])
        }
      }
    } catch (error) {
      setErrorMessage('Unable to fetch duplicate progress.')
    }
  }

  useEffect(() => {
    if (!jobStatus || jobStatus.status === 'completed' || jobStatus.status === 'failed') {
      return undefined
    }
    pollJob(jobStatus.id)
    const interval = setInterval(() => {
      pollJob(jobStatus.id)
    }, 1000)
    return () => clearInterval(interval)
  }, [jobStatus?.id, jobStatus?.status])

  useEffect(() => {
    if (!clusterJob || clusterJob.status === 'completed' || clusterJob.status === 'failed') {
      return undefined
    }
    pollCluster(clusterJob.id)
    const interval = setInterval(() => {
      pollCluster(clusterJob.id)
    }, 1000)
    return () => clearInterval(interval)
  }, [clusterJob?.id, clusterJob?.status])

  useEffect(() => {
    if (!dedupeJob || dedupeJob.status === 'completed' || dedupeJob.status === 'failed') {
      return undefined
    }
    pollDedupe(dedupeJob.id)
    const interval = setInterval(() => {
      pollDedupe(dedupeJob.id)
    }, 1000)
    return () => clearInterval(interval)
  }, [dedupeJob?.id, dedupeJob?.status])

  return (
    <div className="app">
      <header className="header">
        <div>
          <p className="eyebrow">Photo Book Creator</p>
          <h1>Drag photos here to start a book</h1>
          <p className="subtitle">
            Drop folders or image files to create a new project. Originals stay
            in place.
          </p>
        </div>
        <div className="status-card">
          <p className="status-label">Status</p>
          <p className="status-title">{statusText.title}</p>
          <p className="status-subtitle">{statusText.subtitle}</p>
        </div>
      </header>

      <section
        className={`dropzone${isDragging ? ' is-dragging' : ''}`}
        onDragOver={handleDragOver}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <div className="dropzone-inner">
          <div className="dropzone-icon" aria-hidden="true">
            <span />
          </div>
          <div>
            <p className="dropzone-title">Drop images or folders</p>
            <p className="dropzone-subtitle">
              This is a live canvas. Keep adding sources anytime.
            </p>
          </div>
        </div>
      </section>

        <section className="file-list">
        {files.length === 0 ? (
          <div className="empty-list">
            <div>
              <p className="empty-title">No files yet</p>
              <p className="empty-subtitle">
                Drag a few photos to see them listed here.
              </p>
            </div>
          </div>
        ) : (
          <div className="file-list-inner">
            <div className="file-list-header">
              <div>
                <p className="file-list-title">Staged sources</p>
                <p className="file-list-subtitle">
                  These are the files captured from your drop.
                </p>
              </div>
              <button type="button" className="clear-button" onClick={() => setFiles([])}>
                Clear list
              </button>
            </div>
            <ul className="file-items">
              {files.map((entry) => (
                <li
                  key={`${entry.file.name}-${entry.file.lastModified}-${entry.path}`}
                  className="file-item"
                >
                  <div>
                    <p className="file-name">{entry.file.name}</p>
                    <p className="file-meta">
                      {entry.path} · {(entry.file.size / 1024).toFixed(1)} KB ·
                      {entry.file.type || 'Unknown type'}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="actions">
        <div className="file-list-inner">
          <div className="file-list-header">
            <div>
              <p className="file-list-title">Processing tools</p>
              <p className="file-list-subtitle">
                Trigger event clustering and duplicate detection after thumbnails.
              </p>
            </div>
          </div>
          <div className="action-buttons">
            <button
              type="button"
              className="clear-button"
              onClick={triggerCluster}
              disabled={thumbResults.length === 0 || clusterJob?.status === 'running'}
            >
              Cluster events
            </button>
            <button
              type="button"
              className="clear-button"
              onClick={triggerDedupe}
              disabled={thumbResults.length === 0 || dedupeJob?.status === 'running'}
            >
              Find duplicates
            </button>
          </div>
        </div>
      </section>

      <section className="thumb-list">
        <div className="file-list-inner">
          <div className="file-list-header">
            <div>
              <p className="file-list-title">Generated thumbnails</p>
              <p className="file-list-subtitle">
                {thumbResults.length === 0
                  ? 'No thumbnails created yet.'
                  : `Latest run created ${thumbResults.length} thumbnails.`}
              </p>
            </div>
          </div>
          {jobStatus && jobStatus.status !== 'completed' ? (
            <div className="progress-row">
              <div className="progress-bar">
                <span
                  style={{
                    width: `${jobStatus.total ? (jobStatus.completed / jobStatus.total) * 100 : 0}%`,
                  }}
                />
              </div>
              <p className="progress-text">
                {jobStatus.completed} / {jobStatus.total} thumbnails
              </p>
            </div>
          ) : null}
          {errorMessage ? <p className="error-text">{errorMessage}</p> : null}
          <ul className="file-items">
            {thumbResults.map((entry) => (
              <li key={`${entry.photo_path}-${entry.size}`} className="file-item">
                <div>
                  <p className="file-name">{entry.photo_path.split('/').pop()}</p>
                  <p className="file-meta">
                    {entry.size}px · {entry.width}x{entry.height}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="cluster-list">
        <div className="file-list-inner">
          <div className="file-list-header">
            <div>
              <p className="file-list-title">Event clusters</p>
              <p className="file-list-subtitle">
                {clusterResults.length === 0
                  ? 'No clusters yet.'
                  : `Created ${clusterResults.length} clusters.`}
              </p>
            </div>
          </div>
          <ul className="file-items">
            {clusterResults.map((cluster) => (
              <li key={`${cluster.id}-${cluster.name}`} className="file-item">
                <div>
                  <p className="file-name">{cluster.name}</p>
                  <p className="file-meta">
                    {cluster.start_at} - {cluster.end_at} · {cluster.photos.length} photos
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="duplicate-list">
        <div className="file-list-inner">
          <div className="file-list-header">
            <div>
              <p className="file-list-title">Duplicate stacks</p>
              <p className="file-list-subtitle">
                {duplicateResults.length === 0
                  ? 'No duplicate groups yet.'
                  : `Found ${duplicateResults.length} stacks.`}
              </p>
            </div>
          </div>
          <ul className="file-items">
            {duplicateResults.map((group) => (
              <li key={group.id} className="file-item">
                <div>
                  <p className="file-name">Stack {group.id}</p>
                  <p className="file-meta">
                    {group.photos.length} photos · Best: {group.photos.find((photo) => photo.is_best)?.photo_path.split('/').pop()}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  )
}

export default App
