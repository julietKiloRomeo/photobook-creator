import { useEffect, useMemo, useRef, useState } from 'react'
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
  const [activeStage, setActiveStage] = useState('intake')
  const [selectedStackId, setSelectedStackId] = useState(null)
  const fileInputRef = useRef(null)
  const folderInputRef = useRef(null)

  const stageMeta = useMemo(
    () => ({
      intake: {
        title: 'Intake',
        subtitle: 'Bring sources into the project without leaving the page.',
      },
      thumbnails: {
        title: 'Thumbnails',
        subtitle: 'Preview cached thumbnails and monitor pipeline progress.',
      },
      clusters: {
        title: 'Clusters',
        subtitle: 'Review event groupings and time ranges.',
      },
      duplicates: {
        title: 'Duplicates',
        subtitle: 'Scan stacks and confirm the best shot.',
      },
    }),
    [],
  )

  const stages = useMemo(
    () => [
      { id: 'intake', label: 'Intake' },
      { id: 'thumbnails', label: 'Thumbnails' },
      { id: 'clusters', label: 'Clusters' },
      { id: 'duplicates', label: 'Duplicates' },
    ],
    [],
  )

  const activeJob = useMemo(() => {
    if (jobStatus && !['completed', 'failed'].includes(jobStatus.status)) {
      return { title: 'Building thumbnails', stage: 'Thumbnails', job: jobStatus }
    }
    if (clusterJob && !['completed', 'failed'].includes(clusterJob.status)) {
      return { title: 'Clustering events', stage: 'Clusters', job: clusterJob }
    }
    if (dedupeJob && !['completed', 'failed'].includes(dedupeJob.status)) {
      return { title: 'Detecting duplicates', stage: 'Duplicates', job: dedupeJob }
    }
    return null
  }, [jobStatus, clusterJob, dedupeJob])

  const lastSummary = useMemo(() => {
    if (duplicateResults.length > 0) {
      return `Last run found ${duplicateResults.length} stack${
        duplicateResults.length === 1 ? '' : 's'
      }.`
    }
    if (clusterResults.length > 0) {
      return `Last run created ${clusterResults.length} cluster${
        clusterResults.length === 1 ? '' : 's'
      }.`
    }
    if (thumbResults.length > 0) {
      return `Last run generated ${thumbResults.length} thumbnails.`
    }
    if (files.length > 0) {
      return `${files.length} source${files.length === 1 ? '' : 's'} staged.`
    }
    return 'Ready when you are.'
  }, [clusterResults.length, duplicateResults.length, files.length, thumbResults.length])

  const progressPercent = activeJob?.job?.total
    ? Math.round((activeJob.job.completed / activeJob.job.total) * 100)
    : 0

  const progressDetail = activeJob
    ? `${activeJob.job.completed ?? 0} of ${activeJob.job.total ?? 0} complete`
    : lastSummary

  useEffect(() => {
    if (duplicateResults.length === 0) {
      setSelectedStackId(null)
      return
    }
    if (!duplicateResults.some((group) => group.id === selectedStackId)) {
      setSelectedStackId(duplicateResults[0].id)
    }
  }, [duplicateResults, selectedStackId])

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

  function queueFiles(entries) {
    const nextFiles = []
    setFiles((prev) => {
      const existing = new Set(
        prev.map((entry) => `${entry.file.name}-${entry.file.lastModified}-${entry.path}`),
      )
      const next = [...prev]
      entries.forEach((entry) => {
        const key = `${entry.file.name}-${entry.file.lastModified}-${entry.path}`
        if (!existing.has(key)) {
          existing.add(key)
          next.push(entry)
          nextFiles.push(entry)
        }
      })
      return next
    })
    return nextFiles
  }

  async function uploadFiles(nextFiles) {
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

  async function handleDrop(event) {
    event.preventDefault()
    setIsDragging(false)
    setErrorMessage('')
    const droppedFiles = await collectFilesFromDataTransfer(event.dataTransfer)
    if (droppedFiles.length === 0) {
      return
    }
    const nextFiles = queueFiles(droppedFiles)
    await uploadFiles(nextFiles)
  }

  async function handleFileSelection(fileList) {
    const entries = Array.from(fileList ?? [])
      .map((file) => ({ file, path: file.webkitRelativePath || file.name }))
      .filter(isPhotoFile)
    if (entries.length === 0) {
      return
    }
    const nextFiles = queueFiles(entries)
    await uploadFiles(nextFiles)
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
      <header className="app-header">
        <div className="brand">
          <p className="brand-kicker">Photo Book Creator</p>
          <h1 className="brand-title">Project: 2026 Annual</h1>
          <p className="brand-subtitle">
            A no-scroll workspace for intake, clustering, and duplicate review.
          </p>
        </div>

        <div className="stage-controls">
          <div className="stage-tabs" role="tablist" aria-label="Workflow stages">
            {stages.map((stage) => (
              <button
                key={stage.id}
                type="button"
                role="tab"
                aria-selected={activeStage === stage.id}
                className={activeStage === stage.id ? 'is-active' : ''}
                onClick={() => setActiveStage(stage.id)}
              >
                {stage.label}
              </button>
            ))}
          </div>
          <select
            className="stage-select"
            value={activeStage}
            onChange={(event) => setActiveStage(event.target.value)}
            aria-label="Select a stage"
          >
            {stages.map((stage) => (
              <option key={stage.id} value={stage.id}>
                {stage.label}
              </option>
            ))}
          </select>
        </div>

        <div className="progress-banner">
          <div>
            <p className="progress-label">Global progress</p>
            <p className="progress-title">{activeJob ? activeJob.title : 'No active jobs'}</p>
            <p className="progress-subtitle">
              {activeJob ? `Stage ${activeJob.stage} · ${progressPercent}%` : 'Idle'}
            </p>
            <p className="progress-detail">{progressDetail}</p>
          </div>
          <div className="progress-meter">
            <span style={{ width: `${progressPercent}%` }} />
          </div>
        </div>
      </header>

      <div className="app-body">
        <main className="stage-panel">
          <div className="stage-header">
            <div>
              <p className="stage-kicker">Current stage</p>
              <h2>{stageMeta[activeStage].title}</h2>
              <p className="stage-subtitle">{stageMeta[activeStage].subtitle}</p>
            </div>
            <div className="stage-actions">
              {activeStage === 'clusters' ? (
                <button
                  type="button"
                  className="action-button"
                  onClick={triggerCluster}
                  disabled={
                    thumbResults.length === 0 ||
                    ['running', 'queued'].includes(clusterJob?.status)
                  }
                >
                  Run clustering
                </button>
              ) : null}
              {activeStage === 'duplicates' ? (
                <button
                  type="button"
                  className="action-button"
                  onClick={triggerDedupe}
                  disabled={
                    thumbResults.length === 0 ||
                    ['running', 'queued'].includes(dedupeJob?.status)
                  }
                >
                  Find duplicates
                </button>
              ) : null}
              {activeStage === 'intake' ? (
                <button
                  type="button"
                  className="action-button"
                  onClick={() => setFiles([])}
                  disabled={files.length === 0}
                >
                  Clear sources
                </button>
              ) : null}
            </div>
          </div>

          <div className={`stage-grid stage-grid--${activeStage}`}>
            {activeStage === 'intake' ? (
              <>
                <section
                  className={`stage-card dropzone-card${isDragging ? ' is-dragging' : ''}`}
                  onDragOver={handleDragOver}
                  onDragEnter={handleDragEnter}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                >
                  <div className="dropzone-content">
                    <div className="dropzone-icon" aria-hidden="true">
                      <span />
                    </div>
                    <div>
                      <p className="card-title">Drop images or folders</p>
                      <p className="card-subtitle">
                        This canvas stays active while background jobs run.
                      </p>
                    </div>
                  </div>
                </section>
                <section className="stage-card">
                  <div className="card-header">
                    <div>
                      <p className="card-title">Add sources</p>
                      <p className="card-subtitle">Drop, pick a folder, or link a URL.</p>
                    </div>
                  </div>
                  <div className="button-row">
                    <button type="button" onClick={() => folderInputRef.current?.click()}>
                      Add folder
                    </button>
                    <button type="button" onClick={() => fileInputRef.current?.click()}>
                      Add files
                    </button>
                    <button type="button" className="secondary" disabled>
                      Add URL
                    </button>
                  </div>
                  <p className="helper-text">URL intake is queued for a later milestone.</p>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept="image/*"
                    className="file-input"
                    onChange={(event) => {
                      handleFileSelection(event.target.files)
                      event.target.value = ''
                    }}
                  />
                  <input
                    ref={folderInputRef}
                    type="file"
                    multiple
                    accept="image/*"
                    webkitdirectory="true"
                    className="file-input"
                    onChange={(event) => {
                      handleFileSelection(event.target.files)
                      event.target.value = ''
                    }}
                  />
                </section>
                <section className="stage-card">
                  <div className="card-header">
                    <div>
                      <p className="card-title">Staged sources</p>
                      <p className="card-subtitle">Showing up to 6 entries.</p>
                    </div>
                  </div>
                  {files.length === 0 ? (
                    <div className="empty-state">
                      <p className="empty-title">No sources yet</p>
                      <p className="empty-subtitle">Drop images to start the pipeline.</p>
                    </div>
                  ) : (
                    <>
                      <ul className="compact-list">
                        {files.slice(0, 6).map((entry) => (
                          <li
                            key={`${entry.file.name}-${entry.file.lastModified}-${entry.path}`}
                          >
                            <div>
                              <p className="item-title">{entry.file.name}</p>
                              <p className="item-meta">
                                {entry.path} · {(entry.file.size / 1024).toFixed(1)} KB
                              </p>
                            </div>
                          </li>
                        ))}
                      </ul>
                      {files.length > 6 ? (
                        <p className="more-count">+{files.length - 6} more</p>
                      ) : null}
                    </>
                  )}
                </section>
              </>
            ) : null}

            {activeStage === 'thumbnails' ? (
              <>
                <section className="stage-card">
                  <div className="card-header">
                    <div>
                      <p className="card-title">Thumbnail preview</p>
                      <p className="card-subtitle">Latest cache snapshot (10 max).</p>
                    </div>
                  </div>
                  {thumbResults.length === 0 ? (
                    <div className="empty-state">
                      <p className="empty-title">No thumbnails yet</p>
                      <p className="empty-subtitle">Ingest photos to start rendering.</p>
                    </div>
                  ) : (
                    <div className="thumb-grid">
                      {thumbResults.slice(0, 10).map((entry) => (
                        <div key={`${entry.photo_path}-${entry.size}`} className="thumb-tile">
                          <span>{entry.photo_path.split('/').pop()}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </section>
                <section className="stage-card">
                  <div className="card-header">
                    <div>
                      <p className="card-title">Status & cache</p>
                      <p className="card-subtitle">Pipeline health and cache footprint.</p>
                    </div>
                  </div>
                  <div className="stat-grid">
                    <div>
                      <p className="stat-label">Cache items</p>
                      <p className="stat-value">{thumbResults.length}</p>
                    </div>
                    <div>
                      <p className="stat-label">Upload state</p>
                      <p className="stat-value">{isUploading ? 'Uploading' : 'Idle'}</p>
                    </div>
                  </div>
                  {jobStatus && jobStatus.status !== 'completed' ? (
                    <div className="progress-row">
                      <div className="progress-bar">
                        <span
                          style={{
                            width: `${
                              jobStatus.total
                                ? (jobStatus.completed / jobStatus.total) * 100
                                : 0
                            }%`,
                          }}
                        />
                      </div>
                      <p className="progress-text">
                        {jobStatus.completed ?? 0} / {jobStatus.total ?? 0} complete
                      </p>
                    </div>
                  ) : (
                    <p className="helper-text">No active thumbnail job.</p>
                  )}
                </section>
              </>
            ) : null}

            {activeStage === 'clusters' ? (
              <>
                <section className="stage-card">
                  <div className="card-header">
                    <div>
                      <p className="card-title">Cluster cards</p>
                      <p className="card-subtitle">Showing up to 6 events.</p>
                    </div>
                  </div>
                  {clusterResults.length === 0 ? (
                    <div className="empty-state">
                      <p className="empty-title">No clusters yet</p>
                      <p className="empty-subtitle">Run clustering after thumbnails.</p>
                    </div>
                  ) : (
                    <ul className="compact-list">
                      {clusterResults.slice(0, 6).map((cluster) => (
                        <li key={`${cluster.id}-${cluster.name}`}>
                          <div>
                            <p className="item-title">{cluster.name}</p>
                            <p className="item-meta">
                              {cluster.start_at} - {cluster.end_at} · {cluster.photos.length}{' '}
                              photos
                            </p>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                  {clusterResults.length > 6 ? (
                    <p className="more-count">+{clusterResults.length - 6} more</p>
                  ) : null}
                </section>
                <section className="stage-card">
                  <div className="card-header">
                    <div>
                      <p className="card-title">Summary</p>
                      <p className="card-subtitle">High level readout for the run.</p>
                    </div>
                  </div>
                  <div className="stat-grid">
                    <div>
                      <p className="stat-label">Clusters</p>
                      <p className="stat-value">{clusterResults.length}</p>
                    </div>
                    <div>
                      <p className="stat-label">Time range</p>
                      <p className="stat-value">
                        {clusterResults.length > 0
                          ? `${clusterResults[0].start_at} - ${
                              clusterResults[clusterResults.length - 1].end_at
                            }`
                          : '—'}
                      </p>
                    </div>
                  </div>
                  {clusterJob && clusterJob.status !== 'completed' ? (
                    <p className="helper-text">Job status: {clusterJob.status}</p>
                  ) : (
                    <p className="helper-text">Last run ready to review.</p>
                  )}
                </section>
              </>
            ) : null}

            {activeStage === 'duplicates' ? (
              <>
                <section className="stage-card">
                  <div className="card-header">
                    <div>
                      <p className="card-title">Stacks</p>
                      <p className="card-subtitle">Showing up to 6 stacks.</p>
                    </div>
                  </div>
                  {duplicateResults.length === 0 ? (
                    <div className="empty-state">
                      <p className="empty-title">No duplicate stacks</p>
                      <p className="empty-subtitle">Run duplicate detection to begin.</p>
                    </div>
                  ) : (
                    <ul className="stack-list">
                      {duplicateResults.slice(0, 6).map((group) => (
                        <li key={group.id}>
                          <button
                            type="button"
                            className={
                              group.id === selectedStackId
                                ? 'stack-button is-selected'
                                : 'stack-button'
                            }
                            onClick={() => setSelectedStackId(group.id)}
                          >
                            <div>
                              <p className="item-title">Stack {group.id}</p>
                              <p className="item-meta">{group.photos.length} photos</p>
                            </div>
                            <span className="stack-count">{group.photos.length}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                  {duplicateResults.length > 6 ? (
                    <p className="more-count">+{duplicateResults.length - 6} more</p>
                  ) : null}
                </section>
                <section className="stage-card">
                  <div className="card-header">
                    <div>
                      <p className="card-title">Selected stack</p>
                      <p className="card-subtitle">Preview up to 4 frames.</p>
                    </div>
                  </div>
                  {selectedStackId && duplicateResults.length > 0 ? (
                    <>
                      <div className="thumb-grid compact">
                        {duplicateResults
                          .find((group) => group.id === selectedStackId)
                          ?.photos.slice(0, 4)
                          .map((photo) => (
                            <div key={photo.photo_path} className="thumb-tile">
                              <span>{photo.photo_path.split('/').pop()}</span>
                              {photo.is_best ? (
                                <span className="best-badge">Best</span>
                              ) : null}
                            </div>
                          ))}
                      </div>
                      <p className="helper-text">
                        Best shot:{' '}
                        {
                          duplicateResults
                            .find((group) => group.id === selectedStackId)
                            ?.photos.find((photo) => photo.is_best)?.photo_path
                            ?.split('/').pop() || '—'
                        }
                      </p>
                    </>
                  ) : (
                    <div className="empty-state">
                      <p className="empty-title">Pick a stack</p>
                      <p className="empty-subtitle">Select a stack to inspect frames.</p>
                    </div>
                  )}
                </section>
              </>
            ) : null}
          </div>
        </main>

        <aside className="status-rail">
          <div className="rail-card">
            <div className="card-header">
              <div>
                <p className="card-title">Job queue</p>
                <p className="card-subtitle">Queued, running, and completed.</p>
              </div>
            </div>
            <ul className="job-list">
              {[
                { label: 'Thumbnails', stage: 'Intake', job: jobStatus },
                { label: 'Clusters', stage: 'Clusters', job: clusterJob },
                { label: 'Duplicates', stage: 'Duplicates', job: dedupeJob },
              ].map((item) => (
                <li key={item.label} className="job-item">
                  <div>
                    <p className="item-title">{item.label}</p>
                    <p className="item-meta">{item.stage}</p>
                  </div>
                  <span className={`status-pill status-${item.job?.status ?? 'idle'}`}>
                    {item.job?.status ?? 'idle'}
                  </span>
                </li>
              ))}
            </ul>
          </div>
          <div className="rail-card">
            <div className="card-header">
              <div>
                <p className="card-title">Recent outcomes</p>
                <p className="card-subtitle">Last completed pipeline step.</p>
              </div>
            </div>
            <div className="stat-grid">
              <div>
                <p className="stat-label">Sources</p>
                <p className="stat-value">{files.length}</p>
              </div>
              <div>
                <p className="stat-label">Thumbnails</p>
                <p className="stat-value">{thumbResults.length}</p>
              </div>
              <div>
                <p className="stat-label">Clusters</p>
                <p className="stat-value">{clusterResults.length}</p>
              </div>
              <div>
                <p className="stat-label">Stacks</p>
                <p className="stat-value">{duplicateResults.length}</p>
              </div>
            </div>
          </div>
          <div className="rail-card">
            <div className="card-header">
              <div>
                <p className="card-title">System health</p>
                <p className="card-subtitle">Background services and alerts.</p>
              </div>
            </div>
            {errorMessage ? (
              <div className="alert">
                <p className="alert-title">Action needed</p>
                <p className="alert-text">{errorMessage}</p>
              </div>
            ) : (
              <div className="health-grid">
                <div>
                  <p className="stat-label">Thumbnail API</p>
                  <p className="stat-value">Online</p>
                </div>
                <div>
                  <p className="stat-label">Cluster worker</p>
                  <p className="stat-value">Standing by</p>
                </div>
                <div>
                  <p className="stat-label">Dedupe worker</p>
                  <p className="stat-value">Standing by</p>
                </div>
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}

export default App
