import { useEffect, useMemo, useRef, useState } from 'react'

function App() {
  const [files, setFiles] = useState([])
  const [thumbResults, setThumbResults] = useState([])
  const [clusterResults, setClusterResults] = useState([])
  const [duplicateResults, setDuplicateResults] = useState([])
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [jobStatus, setJobStatus] = useState(null)
  const [clusterJob, setClusterJob] = useState(null)
  const [dedupeJob, setDedupeJob] = useState(null)
  const [scoreJob, setScoreJob] = useState(null)
  const [isDragging, setIsDragging] = useState(false)
  const [activeStage, setActiveStage] = useState('intake')
  const [selectedStackId, setSelectedStackId] = useState(null)
  const [scoreResults, setScoreResults] = useState([])
  const [chapters, setChapters] = useState([])
  const [selectedChapterId, setSelectedChapterId] = useState(null)
  const [pages, setPages] = useState([])
  const [selectedPageId, setSelectedPageId] = useState(null)
  const [pageItems, setPageItems] = useState([])
  const [newChapterName, setNewChapterName] = useState('')
  const [pageCountDraft, setPageCountDraft] = useState('')
  const [layoutItemCount, setLayoutItemCount] = useState(0)
  const [buildPalette, setBuildPalette] = useState([])
  const [exportPayload, setExportPayload] = useState(null)
  const [isExporting, setIsExporting] = useState(false)
  const [selectedLayoutItemId, setSelectedLayoutItemId] = useState(null)
  const [dragPayload, setDragPayload] = useState(null)
  const [layoutFilter, setLayoutFilter] = useState('all')
  const [layoutSort, setLayoutSort] = useState('name')
  const [isDrawerOpen, setIsDrawerOpen] = useState(false)
  const [bestOverrides, setBestOverrides] = useState({})
  const [recentAdvance, setRecentAdvance] = useState(null)
  const fileInputRef = useRef(null)
  const folderInputRef = useRef(null)
  const filesRef = useRef([])
  const previousThumbCount = useRef(0)
  const previousChapterCount = useRef(0)

  const stageMeta = useMemo(
    () => ({
      intake: {
        title: 'Intake',
        subtitle: 'Drop sources and let the pipeline run.',
      },
      clean: {
        title: 'Clean',
        subtitle: 'Confirm thumbnails and choose best shots.',
      },
      organize: {
        title: 'Organize',
        subtitle: 'Review clusters to shape chapters.',
      },
      build: {
        title: 'Build',
        subtitle: 'Lay out chapters, pages, and staging.',
      },
      export: {
        title: 'Export',
        subtitle: 'Preview and export the JSON package.',
      },
    }),
    [],
  )

  const stages = useMemo(
    () => [
      { id: 'intake', label: 'Intake' },
      { id: 'clean', label: 'Clean' },
      { id: 'organize', label: 'Organize' },
      { id: 'build', label: 'Build' },
      { id: 'export', label: 'Export' },
    ],
    [],
  )

  const activeJob = useMemo(() => {
    if (jobStatus && !['completed', 'failed'].includes(jobStatus.status)) {
      return { title: 'Building thumbnails', stage: 'Clean', job: jobStatus }
    }
    if (clusterJob && !['completed', 'failed'].includes(clusterJob.status)) {
      return { title: 'Clustering events', stage: 'Organize', job: clusterJob }
    }
    if (dedupeJob && !['completed', 'failed'].includes(dedupeJob.status)) {
      return { title: 'Detecting duplicates', stage: 'Clean', job: dedupeJob }
    }
    if (scoreJob && !['completed', 'failed'].includes(scoreJob.status)) {
      return { title: 'Scoring aesthetics', stage: 'Clean', job: scoreJob }
    }
    return null
  }, [jobStatus, clusterJob, dedupeJob, scoreJob])

  const lastSummary = useMemo(() => {
    if (duplicateResults.length > 0) {
      return `Last run found ${duplicateResults.length} stack${
        duplicateResults.length === 1 ? '' : 's'
      }.`
    }
    if (scoreResults.length > 0) {
      return `Last run scored ${scoreResults.length} photos.`
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
  }, [
    clusterResults.length,
    duplicateResults.length,
    files.length,
    scoreResults.length,
    thumbResults.length,
  ])

  const isUploadingNow = Boolean(isUploading && uploadProgress?.total)
  const uploadCompleted = uploadProgress?.completed ?? 0
  const uploadTotal = uploadProgress?.total ?? 0

  const progressPercent = isUploadingNow
    ? Math.round((uploadCompleted / uploadTotal) * 100)
    : activeJob?.job?.total
      ? Math.round((activeJob.job.completed / activeJob.job.total) * 100)
      : activeJob
        ? 8
        : 0

  const progressDetail = isUploadingNow
    ? `Uploading ${uploadCompleted} of ${uploadTotal}`
    : activeJob
      ? `${activeJob.job.completed ?? 0} of ${activeJob.job.total ?? 0} complete`
      : lastSummary

  const nextStepText = useMemo(() => {
    if (activeStage === 'intake') {
      if (files.length === 0) {
        return 'Next: add sources to start the pipeline.'
      }
      if (isUploading || activeJob) {
        return 'Next: thumbnails are processing. Clean will open when ready.'
      }
      if (thumbResults.length > 0) {
        return 'Next: review thumbnails in Clean.'
      }
      return 'Next: move to Clean to confirm thumbnails.'
    }
    if (activeStage === 'clean') {
      if (thumbResults.length === 0) {
        return 'Next: run thumbnail generation from Intake.'
      }
      if (duplicateResults.length === 0) {
        return 'Next: duplicate detection is running.'
      }
      return 'Next: confirm best shots, then review clusters.'
    }
    if (activeStage === 'organize') {
      return 'Next: create a chapter from a cluster.'
    }
    if (activeStage === 'build') {
      return 'Next: build chapters and page layouts.'
    }
    return 'Next: export the final JSON package.'
  }, [activeStage, files.length, isUploading, activeJob, thumbResults.length])

  const nextStepMarkup = useMemo(() => {
    const [prefix, suffix] = nextStepText.split(': ')
    if (!suffix) {
      return nextStepText
    }
    return (
      <>
        <strong>{prefix}:</strong> {suffix}
      </>
    )
  }, [nextStepText])

  const nextStepStatus = useMemo(() => {
    if (activeStage === 'intake') {
      if (files.length === 0) {
        return 'pending'
      }
      if (isUploading || activeJob) {
        return 'processing'
      }
      if (thumbResults.length > 0) {
        return 'ready'
      }
      return 'pending'
    }
    if (activeStage === 'clean') {
      if (thumbResults.length === 0) {
        return 'pending'
      }
      if (duplicateResults.length === 0) {
        return 'processing'
      }
      return 'ready'
    }
    if (activeStage === 'organize') {
      return clusterResults.length > 0 ? 'ready' : 'pending'
    }
    if (activeStage === 'build') {
      return pages.length > 0 ? 'ready' : 'pending'
    }
    return exportPayload ? 'ready' : 'pending'
  }, [
    activeStage,
    files.length,
    isUploading,
    activeJob,
    thumbResults.length,
    duplicateResults.length,
    clusterResults.length,
    pages.length,
    exportPayload,
  ])

  const sortedStacks = useMemo(() => {
    const stacks = [...duplicateResults]
    stacks.sort((left, right) => {
      const leftResolved = Boolean(left.resolved)
      const rightResolved = Boolean(right.resolved)
      if (leftResolved !== rightResolved) {
        return leftResolved ? 1 : -1
      }
      return left.id - right.id
    })
    return stacks
  }, [duplicateResults])

  const selectedStack = useMemo(
    () => sortedStacks.find((group) => group.id === selectedStackId) ?? null,
    [sortedStacks, selectedStackId],
  )

  const uniqueStackPhotos = useMemo(() => {
    if (!selectedStack) {
      return []
    }
    const seen = new Set()
    const unique = []
    for (const photo of selectedStack.photos ?? []) {
      const filename = photo.photo_path?.split('/').pop() ?? photo.photo_path
      if (!filename || seen.has(filename)) {
        continue
      }
      seen.add(filename)
      unique.push(photo)
    }
    return unique
  }, [selectedStack])

  const bestPhotoPath = useMemo(() => {
    if (!selectedStack || !selectedStackId) {
      return null
    }
    const overridePath = bestOverrides[selectedStackId]
    if (overridePath) {
      return overridePath
    }
    const bestPhoto = (selectedStack.photos ?? []).find((photo) => photo.is_best)
    return bestPhoto?.photo_path ?? selectedStack.photos?.[0]?.photo_path ?? null
  }, [selectedStack, selectedStackId, bestOverrides])

  const thumbPathMap = useMemo(() => {
    const map = new Map()
    thumbResults.forEach((entry) => {
      if (entry.size === 256) {
        map.set(entry.photo_path, entry.path)
      }
    })
    return map
  }, [thumbResults])

  const selectedStackBestThumbnail = useMemo(() => {
    if (!selectedStack) {
      return null
    }
    const overridePath = bestOverrides[selectedStack.id]
    const bestPhoto = overridePath
      ? selectedStack.photos?.find((photo) => photo.photo_path === overridePath)
      : selectedStack.photos?.find((photo) => photo.is_best) ?? selectedStack.photos?.[0]
    if (!bestPhoto) {
      return null
    }
    return (
      bestPhoto.thumb_path ||
      thumbPathMap.get(bestPhoto.photo_path) ||
      bestPhoto.path ||
      null
    )
  }, [selectedStack, bestOverrides, thumbPathMap])

  useEffect(() => {
    if (duplicateResults.length === 0) {
      setSelectedStackId(null)
      return
    }
    if (!duplicateResults.some((group) => group.id === selectedStackId)) {
      setSelectedStackId(duplicateResults[0].id)
    }
  }, [duplicateResults, selectedStackId])

  useEffect(() => {
    if (duplicateResults.length === 0) {
      setBestOverrides({})
      return
    }
    setBestOverrides((prev) => {
      const next = { ...prev }
      const validIds = new Set(duplicateResults.map((group) => group.id))
      Object.keys(next).forEach((id) => {
        if (!validIds.has(Number(id)) && !validIds.has(String(id))) {
          delete next[id]
        }
      })
      return next
    })
  }, [duplicateResults])

  async function fetchThumbnails() {
    try {
      const response = await fetch('/api/thumbnails')
      if (!response.ok) {
        throw new Error('Thumbnail lookup failed')
      }
      const data = await response.json()
      setThumbResults(data.items ?? [])
    } catch (error) {
      setErrorMessage('Unable to load thumbnails.')
    }
  }

  async function fetchDuplicates() {
    try {
      const response = await fetch('/api/duplicates')
      if (!response.ok) {
        throw new Error('Duplicate lookup failed')
      }
      const data = await response.json()
      setDuplicateResults(data.items ?? [])
    } catch (error) {
      setErrorMessage('Unable to load duplicate stacks.')
    }
  }

  async function ignoreStack(stackId) {
    if (!stackId) {
      return
    }
    try {
      const response = await fetch('/api/duplicates/ignore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ group_id: stackId }),
      })
      if (!response.ok) {
        throw new Error('Ignore stack failed')
      }
      await fetchDuplicates()
    } catch (error) {
      setErrorMessage('Unable to ignore stack.')
    }
  }

  async function ignorePhoto(photoPath) {
    if (!photoPath) {
      return
    }
    try {
      const response = await fetch('/api/duplicates/ignore-photo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ photo_path: photoPath }),
      })
      if (!response.ok) {
        throw new Error('Ignore photo failed')
      }
      await fetchDuplicates()
    } catch (error) {
      setErrorMessage('Unable to ignore photo.')
    }
  }

  async function deleteStack(stackId) {
    if (!stackId) {
      return
    }
    try {
      const response = await fetch('/api/duplicates/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ group_id: stackId }),
      })
      if (!response.ok) {
        throw new Error('Delete stack failed')
      }
      await fetchDuplicates()
      await fetchThumbnails()
    } catch (error) {
      setErrorMessage('Unable to delete stack photos.')
    }
  }

  async function deletePhoto(photoPath) {
    if (!photoPath) {
      return
    }
    try {
      const response = await fetch('/api/duplicates/delete-photo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ photo_path: photoPath }),
      })
      if (!response.ok) {
        throw new Error('Delete photo failed')
      }
      await fetchDuplicates()
      await fetchThumbnails()
    } catch (error) {
      setErrorMessage('Unable to delete photo.')
    }
  }

  async function resolveStack(stackId, resolved) {
    if (!stackId) {
      return
    }
    try {
      const response = await fetch('/api/duplicates/resolve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ group_id: stackId, resolved }),
      })
      if (!response.ok) {
        throw new Error('Resolve stack failed')
      }
      await fetchDuplicates()
    } catch (error) {
      setErrorMessage('Unable to update stack status.')
    }
  }

  useEffect(() => {
    if (chapters.length === 0) {
      setSelectedChapterId(null)
      return
    }
    if (!chapters.some((chapter) => chapter.id === selectedChapterId)) {
      setSelectedChapterId(chapters[0].id)
    }
  }, [chapters, selectedChapterId])

  useEffect(() => {
    if (pages.length === 0) {
      setSelectedPageId(null)
      return
    }
    if (!pages.some((page) => page.id === selectedPageId)) {
      setSelectedPageId(pages[0].id)
    }
  }, [pages, selectedPageId])

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

  useEffect(() => {
    filesRef.current = files
  }, [files])

  function queueFiles(entries) {
    if (entries.length === 0) {
      return []
    }
    const existing = new Set(
      filesRef.current.map((entry) => `${entry.file.name}-${entry.file.lastModified}-${entry.path}`),
    )
    const nextFiles = []
    const next = [...filesRef.current]
    entries.forEach((entry) => {
      const key = `${entry.file.name}-${entry.file.lastModified}-${entry.path}`
      if (!existing.has(key)) {
        existing.add(key)
        next.push(entry)
        nextFiles.push(entry)
      }
    })
    setFiles(next)
    return nextFiles
  }

  async function uploadFiles(nextFiles) {
    if (nextFiles.length === 0) {
      return
    }

    const batchSize = nextFiles.length > 300 ? 5 : 15
    const batches = []
    for (let i = 0; i < nextFiles.length; i += batchSize) {
      batches.push(nextFiles.slice(i, i + batchSize))
    }

    let completed = 0
    setUploadProgress({ total: nextFiles.length, completed })
    setIsUploading(true)
    setErrorMessage('')

    const uploadBatch = async (batch, attempt = 1) => {
      const controller = new AbortController()
      const timeoutId = window.setTimeout(() => controller.abort(), 60000)
      const formData = new FormData()
      batch.forEach((entry) => {
        formData.append('files', entry.file, entry.file.name)
      })

      try {
        const response = await fetch('/api/ingest', {
          method: 'POST',
          body: formData,
          signal: controller.signal,
        })
        if (!response.ok) {
          throw new Error('Upload failed')
        }
        const data = await response.json()
        if (data.job_id) {
          setJobStatus({ id: data.job_id, status: 'queued', total: 0, completed: 0 })
        }
        if (data.cluster_job_id) {
          setClusterJob({
            id: data.cluster_job_id,
            status: 'queued',
            total: data.files?.length ?? batch.length,
            completed: 0,
          })
        }
        completed += batch.length
        setUploadProgress((prev) => ({
          total: prev?.total ?? nextFiles.length,
          completed,
        }))
      } catch (error) {
        if (attempt < 2) {
          return uploadBatch(batch, attempt + 1)
        }
        throw error
      } finally {
        window.clearTimeout(timeoutId)
      }
    }

    try {
      let failedCount = 0
      for (const batch of batches) {
        try {
          await uploadBatch(batch)
        } catch (error) {
          failedCount += batch.length
          completed += batch.length
          setUploadProgress((prev) => ({
            total: prev?.total ?? nextFiles.length,
            completed,
          }))
        }
      }
      if (failedCount > 0) {
        setErrorMessage(`Skipped ${failedCount} files due to upload timeouts.`)
      }
    } finally {
      setIsUploading(false)
      setUploadProgress((prev) =>
        prev
          ? {
              total: prev.total ?? nextFiles.length,
              completed,
            }
          : null,
      )
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

  async function triggerScore() {
    try {
      setErrorMessage('')
      const response = await fetch('/api/score', { method: 'POST' })
      if (!response.ok) {
        throw new Error('Score job failed')
      }
      const data = await response.json()
      if (data.job_id) {
        setScoreJob({ id: data.job_id, status: 'queued', total: 0, completed: 0 })
      }
    } catch (error) {
      setErrorMessage('Unable to start aesthetic scoring.')
    }
  }

  async function fetchChapters() {
    try {
      const response = await fetch('/api/chapters')
      if (!response.ok) {
        throw new Error('Chapter lookup failed')
      }
      const data = await response.json()
      setChapters(data.items ?? [])
    } catch (error) {
      setErrorMessage('Unable to load chapters.')
    }
  }

  async function fetchPages(chapterId) {
    if (!chapterId) {
      setPages([])
      return
    }
    const response = await fetch(`/api/chapters/${chapterId}/pages`)
    if (!response.ok) {
      throw new Error('Page lookup failed')
    }
    const data = await response.json()
    setPages(data.items ?? [])
  }

  async function fetchPageItems(pageId) {
    if (!pageId) {
      setPageItems([])
      return
    }
    const response = await fetch(`/api/pages/${pageId}/items`)
    if (!response.ok) {
      throw new Error('Page items lookup failed')
    }
    const data = await response.json()
    setPageItems(data.items ?? [])
    setLayoutItemCount(data.items?.length ?? 0)
    if (selectedLayoutItemId) {
      const exists = (data.items ?? []).some((item) => item.id === selectedLayoutItemId)
      if (!exists) {
        setSelectedLayoutItemId(null)
      }
    }
  }

  async function createChapter(name, pageCount = Number(pageCountDraft) || 0) {
    if (!name.trim()) {
      return
    }
    try {
      setErrorMessage('')
      const response = await fetch('/api/chapters', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          page_count: pageCount,
        }),
      })
      if (!response.ok) {
        throw new Error('Create chapter failed')
      }
      setNewChapterName('')
      setPageCountDraft('')
      await fetchChapters()
    } catch (error) {
      setErrorMessage('Unable to create chapter.')
    }
  }

  async function handleCreateChapter() {
    await createChapter(newChapterName)
  }

  async function handleUpdatePages() {
    if (!selectedChapterId) {
      return
    }
    try {
      setErrorMessage('')
      const response = await fetch(`/api/chapters/${selectedChapterId}/pages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          page_count: Number(pageCountDraft) || 0,
        }),
      })
      if (!response.ok) {
        throw new Error('Update pages failed')
      }
      setPageCountDraft('')
      await fetchChapters()
      await fetchPages(selectedChapterId)
    } catch (error) {
      setErrorMessage('Unable to update page count.')
    }
  }

  async function handleAddTextItem() {
    if (!selectedPageId) {
      return
    }
    try {
      setErrorMessage('')
      const response = await fetch(`/api/pages/${selectedPageId}/items`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          item_type: 'text',
          text: 'Caption',
          x: 0.1,
          y: 0.1,
          w: 0.8,
          h: 0.2,
          z: 0,
        }),
      })
      if (!response.ok) {
        throw new Error('Create item failed')
      }
      await fetchPageItems(selectedPageId)
    } catch (error) {
      setErrorMessage('Unable to add text element.')
    }
  }

  async function fetchBuildPalette() {
    const response = await fetch('/api/thumbnails')
    if (!response.ok) {
      throw new Error('Palette lookup failed')
    }
    const data = await response.json()
    const items = data.items ?? []
    const unique = []
    const seen = new Set()
    for (const item of items) {
      if (!seen.has(item.photo_path)) {
        seen.add(item.photo_path)
        unique.push(item)
      }
    }
    setBuildPalette(unique)
  }

  async function fetchBuildPaletteFromClusters() {
    const response = await fetch('/api/clusters')
    if (!response.ok) {
      throw new Error('Cluster palette lookup failed')
    }
    const data = await response.json()
    const unique = []
    const seen = new Set()
    for (const cluster of data.items ?? []) {
      for (const photo of cluster.photos ?? []) {
        if (!seen.has(photo.photo_path)) {
          seen.add(photo.photo_path)
          unique.push({ photo_path: photo.photo_path })
        }
      }
    }
    setBuildPalette(unique)
  }

  async function fetchBuildPaletteFromDuplicates() {
    const response = await fetch('/api/duplicates')
    if (!response.ok) {
      throw new Error('Duplicate palette lookup failed')
    }
    const data = await response.json()
    const unique = []
    const seen = new Set()
    for (const group of data.items ?? []) {
      const overridePath = bestOverrides[group.id]
      const best = overridePath
        ? group.photos?.find((photo) => photo.photo_path === overridePath)
        : group.photos?.find((photo) => photo.is_best) ?? group.photos?.[0]
      if (best && !seen.has(best.photo_path)) {
        seen.add(best.photo_path)
        unique.push({ photo_path: best.photo_path, score: best.score })
      }
    }
    setBuildPalette(unique)
  }

  async function handleAddPhotoItem(photoPath, x = 0.1, y = 0.1) {
    if (!selectedPageId || !photoPath) {
      return
    }
    try {
      setErrorMessage('')
      const response = await fetch(`/api/pages/${selectedPageId}/items`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          item_type: 'photo',
          photo_path: photoPath,
          x,
          y,
          w: 0.8,
          h: 0.6,
          z: 0,
        }),
      })
      if (!response.ok) {
        throw new Error('Create item failed')
      }
      await fetchPageItems(selectedPageId)
    } catch (error) {
      setErrorMessage('Unable to add photo.')
    }
  }

  async function handleExport() {
    try {
      setErrorMessage('')
      setIsExporting(true)
      const response = await fetch('/api/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      if (!response.ok) {
        throw new Error('Export failed')
      }
      const data = await response.json()
      setExportPayload(data)
    } catch (error) {
      setErrorMessage('Unable to export book data.')
    } finally {
      setIsExporting(false)
    }
  }

  async function handleDownloadExport() {
    if (!exportPayload) {
      return
    }
    const blob = new Blob([JSON.stringify(exportPayload, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'photo-book-export.json'
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  async function handleUpdateItem(itemId, next) {
    if (!itemId) {
      return
    }
    try {
      const response = await fetch(`/api/pages/items/${itemId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(next),
      })
      if (!response.ok) {
        throw new Error('Update item failed')
      }
      await fetchPageItems(selectedPageId)
    } catch (error) {
      setErrorMessage('Unable to update layout item.')
    }
  }

  function handleDragOverCanvas(event) {
    event.preventDefault()
  }

  async function handleDropOnCanvas(event) {
    event.preventDefault()
    if (!selectedPageId || !dragPayload) {
      setDragPayload(null)
      return
    }
    const rect = event.currentTarget.getBoundingClientRect()
    const x = Math.min(Math.max((event.clientX - rect.left) / rect.width, 0), 0.9)
    const y = Math.min(Math.max((event.clientY - rect.top) / rect.height, 0), 0.9)
    if (dragPayload.type === 'palette') {
      await handleAddPhotoItem(dragPayload.photoPath, x, y)
    }
    setDragPayload(null)
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
        await fetchThumbnails()
        setActiveStage('clean')
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
        await fetchDuplicates()
      }
    } catch (error) {
      setErrorMessage('Unable to fetch duplicate progress.')
    }
  }

  async function pollScore(jobId) {
    try {
      const response = await fetch(`/api/jobs/${jobId}`)
      if (!response.ok) {
        throw new Error('Score lookup failed')
      }
      const data = await response.json()
      setScoreJob(data)
      if (data.status === 'completed') {
        const scoreResponse = await fetch('/api/scores')
        if (scoreResponse.ok) {
          const scoreData = await scoreResponse.json()
          setScoreResults(scoreData.items ?? [])
        }
      }
    } catch (error) {
      setErrorMessage('Unable to fetch scoring progress.')
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

  useEffect(() => {
    if (!scoreJob || scoreJob.status === 'completed' || scoreJob.status === 'failed') {
      return undefined
    }
    pollScore(scoreJob.id)
    const interval = setInterval(() => {
      pollScore(scoreJob.id)
    }, 1000)
    return () => clearInterval(interval)
  }, [scoreJob?.id, scoreJob?.status])

  useEffect(() => {
    if (activeStage !== 'build') {
      return
    }
    fetchChapters().catch(() => setErrorMessage('Unable to load chapters.'))
  }, [activeStage])

  useEffect(() => {
    if (activeStage !== 'build') {
      return
    }
    if (layoutFilter === 'clusters') {
      fetchBuildPaletteFromClusters().catch(() => setErrorMessage('Unable to load palette.'))
    } else if (layoutFilter === 'duplicates') {
      fetchBuildPaletteFromDuplicates().catch(() => setErrorMessage('Unable to load palette.'))
    } else {
      fetchBuildPalette().catch(() => setErrorMessage('Unable to load photo palette.'))
    }
  }, [activeStage, layoutFilter, bestOverrides])

  useEffect(() => {
    if (activeStage !== 'build') {
      return
    }
    setIsDrawerOpen(false)
  }, [activeStage])

  useEffect(() => {
    if (activeStage !== 'build') {
      return
    }
    fetchPages(selectedChapterId).catch(() => setErrorMessage('Unable to load pages.'))
  }, [activeStage, selectedChapterId])

  useEffect(() => {
    if (activeStage !== 'build') {
      return
    }
    fetchPageItems(selectedPageId).catch(() => setErrorMessage('Unable to load page items.'))
  }, [activeStage, selectedPageId])

  useEffect(() => {
    if (activeStage !== 'clean') {
      return
    }
    fetchThumbnails().catch(() => setErrorMessage('Unable to load thumbnails.'))
    fetchDuplicates()
  }, [activeStage])

  function handleStageAdvance(nextStage, reason) {
    setActiveStage(nextStage)
    setRecentAdvance({ from: activeStage, to: nextStage, reason })
  }

  useEffect(() => {
    if (!recentAdvance) {
      return
    }
    const timer = window.setTimeout(() => setRecentAdvance(null), 5000)
    return () => window.clearTimeout(timer)
  }, [recentAdvance])

  useEffect(() => {
    if (activeStage !== 'intake') {
      return
    }
    if (previousThumbCount.current === 0 && thumbResults.length > 0) {
      handleStageAdvance('clean', 'Thumbnails ready')
    }
  }, [activeStage, thumbResults.length])

  useEffect(() => {
    previousThumbCount.current = thumbResults.length
  }, [thumbResults.length])

  useEffect(() => {
    if (activeStage !== 'clean') {
      return
    }
    if (duplicateResults.length === 0 && thumbResults.length > 0) {
      if (!dedupeJob || ['failed'].includes(dedupeJob.status)) {
        triggerDedupe().catch(() => setErrorMessage('Unable to start duplicate detection.'))
      }
    }
  }, [activeStage, duplicateResults.length, thumbResults.length, dedupeJob])

  useEffect(() => {
    if (activeStage !== 'organize') {
      return
    }
    if (clusterResults.length === 0 && thumbResults.length > 0) {
      if (!clusterJob || ['failed'].includes(clusterJob.status)) {
        triggerCluster().catch(() => setErrorMessage('Unable to start clustering.'))
      }
    }
  }, [activeStage, clusterResults.length, thumbResults.length, clusterJob])

  useEffect(() => {
    if (activeStage !== 'organize') {
      return
    }
    if (previousChapterCount.current === 0 && chapters.length > 0) {
      handleStageAdvance('build', 'Chapter created')
    }
  }, [activeStage, chapters.length])

  useEffect(() => {
    previousChapterCount.current = chapters.length
  }, [chapters.length])

  return (
    <div className="min-h-screen bg-surface text-ink">
      <header className="border-b border-line/70 bg-paper/70 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-6 lg:flex-row lg:items-center">
          <div className="flex-1">
            <p className="text-xs uppercase tracking-[0.3em] text-muted">Photo Book Creator</p>
            <h1 className="mt-2 font-display text-3xl text-ink">Project: 2026 Annual</h1>
          </div>

            <div className="flex-1">
              <div className="hidden flex-wrap items-center gap-2 lg:flex">
                {stages.map((stage) => (
                  <button
                    key={stage.id}
                  type="button"
                  className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${
                    activeStage === stage.id
                      ? 'border-ink bg-ink text-paper'
                      : 'border-line bg-paper text-muted hover:border-ink/60 hover:text-ink'
                  }`}
                  onClick={() => setActiveStage(stage.id)}
                >
                  {stage.label}
                </button>
              ))}
            </div>
              <select
                className="mt-3 w-full rounded-xl border border-line bg-paper px-3 py-2 text-sm font-semibold text-ink lg:hidden"
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

          <div className="flex-1">
            <div className="rounded-2xl border border-line bg-paper px-4 py-4">
              <p className="text-xs uppercase tracking-[0.2em] text-muted">Status</p>
              <p className="mt-2 text-lg font-semibold text-ink">
                {activeJob ? activeJob.title : 'No active jobs'}
              </p>
              <p className="text-sm text-muted">
                {activeJob ? `Stage ${activeJob.stage} · ${progressPercent}%` : 'Idle'}
              </p>
              <p className="mt-1 text-sm text-muted">{progressDetail}</p>
              <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-line">
                <span
                  className="block h-full rounded-full bg-ink transition-all"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-6">
        <main
          className="rounded-3xl border border-line bg-paper/90 px-6 py-6 transition-all duration-200"
        >
          <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-muted">Current stage</p>
              <h2 className="mt-2 font-display text-2xl text-ink">
                {stageMeta[activeStage].title}
              </h2>
              <p className="mt-1 text-sm text-muted">{stageMeta[activeStage].subtitle}</p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <div
                className={`flex w-full max-w-md flex-1 items-center gap-4 rounded-2xl border px-4 py-3 text-sm ${
                  nextStepStatus === 'ready'
                    ? 'border-ink/50 bg-paper'
                    : nextStepStatus === 'processing'
                      ? 'border-accent/40 bg-accentSoft/40'
                      : 'border-line bg-paper'
                }`}
              >
                <div>
                  <p className="text-xs uppercase tracking-[0.2em] text-muted">Next action</p>
                  <p className="text-sm text-muted">{nextStepMarkup}</p>
                </div>
              </div>
              <button
                type="button"
                className="rounded-full border border-line bg-paper px-4 py-2 text-sm font-semibold text-ink"
                onClick={() => setIsDrawerOpen((prev) => !prev)}
              >
                Details
              </button>
            </div>
          </div>

          {recentAdvance ? (
            <div className="mt-4 flex items-center justify-between rounded-full border border-line bg-paper px-4 py-2 text-xs text-muted">
              <span>
                Moved to {stageMeta[recentAdvance.to].title} · {recentAdvance.reason}
              </span>
              <button
                type="button"
                className="text-xs font-semibold text-ink"
                onClick={() => setActiveStage(recentAdvance.from)}
              >
                Back
              </button>
            </div>
          ) : null}

          <div
            className={`stage-transition mt-6 grid gap-5 transition-opacity duration-200 ${
              activeStage === 'build' ? 'lg:grid-cols-[1fr_1.2fr_0.9fr]' : 'lg:grid-cols-2'
            }`}
          >
            {activeStage === 'intake' ? (
              <>
                <section
                  className={`rounded-2xl border border-dashed px-6 py-6 transition ${
                    isDragging
                      ? 'border-ink bg-paper shadow-soft'
                      : 'border-line bg-paper'
                  }`}
                  onDragOver={handleDragOver}
                  onDragEnter={handleDragEnter}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                >
                  <div className="flex flex-col gap-4">
                    <div>
                      <p className="text-lg font-semibold text-ink">Drop images or folders</p>
                      <p className="text-sm text-muted">
                        Drop, paste, or select sources to start ingest.
                      </p>
                    </div>
                    <button
                      type="button"
                      className="w-fit rounded-full border border-ink bg-ink px-5 py-2 text-sm font-semibold text-paper"
                      onClick={() => fileInputRef.current?.click()}
                    >
                      Choose sources
                    </button>
                    {activeJob ? (
                      <div className="flex items-center gap-3">
                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-line">
                          <span
                            className="block h-full rounded-full bg-ink transition-all"
                            style={{ width: `${progressPercent}%` }}
                          />
                        </div>
                        <p className="text-xs text-muted">{progressDetail}</p>
                      </div>
                    ) : null}
                  </div>
                </section>
                <section className="rounded-2xl border border-line bg-paper px-6 py-6 lg:col-span-2">
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-base font-semibold text-ink">Staged sources</p>
                      <p className="text-sm text-muted">Showing up to 6 entries.</p>
                    </div>
                  </div>
                  {files.length === 0 ? (
                    <div className="mt-4 rounded-xl border border-line bg-paper px-4 py-6 text-center">
                      <p className="text-sm font-semibold text-ink">No sources yet</p>
                      <p className="text-xs text-muted">Drop images to start the pipeline.</p>
                    </div>
                  ) : (
                    <>
                      <ul className="mt-4 space-y-3">
                        {files.slice(0, 6).map((entry) => (
                          <li
                            key={`${entry.file.name}-${entry.file.lastModified}-${entry.path}`}
                            className="rounded-xl border border-line bg-paper px-3 py-3"
                          >
                            <div>
                              <p className="text-sm font-semibold text-ink">{entry.file.name}</p>
                              <p className="text-xs text-muted">
                                {entry.path} · {(entry.file.size / 1024).toFixed(1)} KB
                              </p>
                            </div>
                          </li>
                        ))}
                      </ul>
                      {files.length > 6 ? (
                        <p className="mt-3 text-xs font-semibold text-muted">
                          +{files.length - 6} more
                        </p>
                      ) : null}
                    </>
                  )}
                </section>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept="image/*"
                  className="hidden"
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
                  className="hidden"
                  onChange={(event) => {
                    handleFileSelection(event.target.files)
                    event.target.value = ''
                  }}
                />
              </>
            ) : null}

            {activeStage === 'clean' ? (
              <>
                <section className="rounded-3xl border border-line bg-paper px-6 py-6 lg:col-span-2">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-lg font-semibold text-ink">Choose the best shot</p>
                      <p className="text-sm text-muted">
                        Review the selected stack and click a frame to set the best.
                      </p>
                    </div>
                    <div className="flex items-center gap-2 text-xs font-semibold text-muted">
                      <span className="rounded-full bg-line px-2 py-1 text-ink">
                        Stack {selectedStackId ?? '—'}
                      </span>
                      <span className="rounded-full bg-accentSoft px-2 py-1 text-accent">
                        {duplicateResults.length} stacks
                      </span>
                    </div>
                  </div>
                  {selectedStack ? (
                    <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
                      <button
                        type="button"
                        className={`rounded-full border px-3 py-1.5 font-semibold ${
                          selectedStack.resolved
                            ? 'border-ink bg-ink text-paper'
                            : 'border-line bg-paper text-ink'
                        }`}
                        onClick={() =>
                          resolveStack(selectedStack.id, !selectedStack.resolved)
                        }
                      >
                        {selectedStack.resolved ? 'Resolved' : 'Mark resolved'}
                      </button>
                      <button
                        type="button"
                        className="rounded-full border border-line bg-paper px-3 py-1.5 font-semibold text-ink"
                        onClick={() => ignoreStack(selectedStack.id)}
                      >
                        Ignore stack
                      </button>
                      <button
                        type="button"
                        className="rounded-full border border-accent/40 bg-accentSoft px-3 py-1.5 font-semibold text-accent"
                        onClick={() => deleteStack(selectedStack.id)}
                      >
                        Delete stack photos
                      </button>
                    </div>
                  ) : null}
                  {selectedStackId && duplicateResults.length > 0 ? (
                    <>
                      <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                        {uniqueStackPhotos.slice(0, 8).map((photo) => {
                            const isBest = bestPhotoPath
                              ? photo.photo_path === bestPhotoPath
                              : false
                            const filename = photo.photo_path.split('/').pop()
                            const thumbPath =
                              photo.thumb_path ||
                              thumbPathMap.get(photo.photo_path) ||
                              photo.path
                            return (
                              <button
                                key={photo.photo_path}
                                type="button"
                                className={`relative overflow-hidden rounded-2xl border text-left transition ${
                                  isBest
                                    ? 'border-ink shadow-soft'
                                    : 'border-line hover:border-ink/40'
                                }`}
                                onClick={() =>
                                  setBestOverrides((prev) => ({
                                    ...prev,
                                    [selectedStackId]: photo.photo_path,
                                  }))
                                }
                              >
                                {thumbPath ? (
                                  <img
                                    className="h-40 w-full object-cover"
                                    src={`/api/thumbnail?path=${encodeURIComponent(thumbPath)}`}
                                    alt={filename}
                                  />
                                ) : (
                                  <div className="flex h-40 items-center justify-center bg-paper text-xs text-muted">
                                    No preview
                                  </div>
                                )}
                                <div className="flex items-center justify-between gap-2 px-3 py-2 text-xs">
                                  <span className="truncate text-ink">{filename}</span>
                                  {typeof photo.score === 'number' ? (
                                    <span className="rounded-full bg-line px-2 py-1 text-[10px] font-semibold text-ink">
                                      {photo.score.toFixed(2)}
                                    </span>
                                  ) : null}
                                </div>
                                {isBest ? (
                                  <span className="absolute left-3 top-3 rounded-full bg-ink px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-paper">
                                    Best
                                  </span>
                                ) : null}
                                <div className="absolute right-3 top-3 flex gap-2">
                                  <button
                                    type="button"
                                    className="rounded-full bg-paper/90 px-2 py-1 text-[10px] font-semibold text-ink"
                                    onClick={(event) => {
                                      event.stopPropagation()
                                      ignorePhoto(photo.photo_path)
                                    }}
                                  >
                                    Ignore
                                  </button>
                                  <button
                                    type="button"
                                    className="rounded-full bg-accent/90 px-2 py-1 text-[10px] font-semibold text-paper"
                                    onClick={(event) => {
                                      event.stopPropagation()
                                      deletePhoto(photo.photo_path)
                                    }}
                                  >
                                    Delete
                                  </button>
                                </div>
                              </button>
                            )
                          })}
                      </div>
                      <p className="mt-4 text-xs text-muted">
                        Best shot:{' '}
                        {bestPhotoPath ? bestPhotoPath.split('/').pop() : '—'}
                      </p>
                    </>
                  ) : (
                    <div className="mt-4 rounded-xl border border-line bg-paper px-4 py-6 text-center">
                      <p className="text-sm font-semibold text-ink">Pick a stack</p>
                      <p className="text-xs text-muted">Select a stack to inspect frames.</p>
                    </div>
                  )}
                </section>
                <section className="rounded-2xl border border-line bg-paper px-6 py-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-base font-semibold text-ink">Stacks</p>
                      <p className="text-sm text-muted">Unresolved stacks first.</p>
                    </div>
                    <div className="flex gap-2 text-xs font-semibold text-muted">
                      <span className="rounded-full bg-line px-2 py-1 text-ink">
                        {sortedStacks.filter((stack) => !stack.resolved).length} open
                      </span>
                      <span className="rounded-full bg-accentSoft px-2 py-1 text-accent">
                        {sortedStacks.filter((stack) => stack.resolved).length} resolved
                      </span>
                    </div>
                  </div>
                  {sortedStacks.length === 0 ? (
                    <div className="mt-4 rounded-xl border border-line bg-paper px-4 py-6 text-center">
                      <p className="text-sm font-semibold text-ink">No duplicate stacks</p>
                      <p className="text-xs text-muted">Duplicate detection runs automatically.</p>
                    </div>
                  ) : (
                    <ul className="mt-4 space-y-3">
                      {sortedStacks.map((group) => (
                        <li key={group.id}>
                          <button
                            type="button"
                            className={`flex w-full items-center gap-3 rounded-xl border px-3 py-3 text-left transition ${
                              group.id === selectedStackId
                                ? 'border-ink bg-paper'
                                : 'border-line bg-paper hover:border-ink/50'
                            }`}
                            onClick={() => setSelectedStackId(group.id)}
                          >
                            <div className="h-12 w-12 overflow-hidden rounded-lg border border-line bg-paper">
                              {(() => {
                                const overridePath = bestOverrides[group.id]
                                const bestPhoto = overridePath
                                  ? group.photos?.find(
                                      (photo) => photo.photo_path === overridePath,
                                    )
                                  : group.photos?.find((photo) => photo.is_best) ??
                                    group.photos?.[0]
                                const bestThumb = bestPhoto
                                  ? bestPhoto.thumb_path ||
                                    thumbPathMap.get(bestPhoto.photo_path) ||
                                    bestPhoto.path
                                  : null
                                if (!bestThumb) {
                                  return null
                                }
                                return (
                                  <img
                                    className="h-full w-full object-cover"
                                    src={`/api/thumbnail?path=${encodeURIComponent(bestThumb)}`}
                                    alt={bestPhoto?.photo_path?.split('/').pop() ?? 'Best shot'}
                                  />
                                )
                              })()}
                            </div>
                            <div className="flex-1">
                              <p className="text-sm font-semibold text-ink">Stack {group.id}</p>
                              <p className="text-xs text-muted">
                                {group.photos.length} photos
                              </p>
                            </div>
                            <div className="flex items-center gap-2 text-xs font-semibold">
                              {group.resolved ? (
                                <span className="rounded-full bg-ink px-2 py-1 text-paper">
                                  Resolved
                                </span>
                              ) : (
                                <span className="rounded-full bg-accentSoft px-2 py-1 text-accent">
                                  Open
                                </span>
                              )}
                              <button
                                type="button"
                                className="rounded-full border border-line bg-paper px-2 py-1 text-[10px] font-semibold text-ink"
                                onClick={(event) => {
                                  event.stopPropagation()
                                  resolveStack(group.id, !group.resolved)
                                }}
                              >
                                {group.resolved ? 'Reopen' : 'Resolve'}
                              </button>
                            </div>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              </>
            ) : null}

            {activeStage === 'organize' ? (
              <>
                <section className="rounded-2xl border border-line bg-paper px-6 py-6">
                  <div>
                    <p className="text-base font-semibold text-ink">Clusters</p>
                    <p className="text-sm text-muted">Showing up to 6 events.</p>
                  </div>
                  {clusterResults.length === 0 ? (
                    <div className="mt-4 rounded-xl border border-line bg-paper px-4 py-6 text-center">
                      <p className="text-sm font-semibold text-ink">No clusters yet</p>
                      <p className="text-xs text-muted">Clustering runs automatically.</p>
                    </div>
                  ) : (
                    <ul className="mt-4 space-y-3">
                      {clusterResults.slice(0, 6).map((cluster) => (
                        <li
                          key={`${cluster.id}-${cluster.name}`}
                          className="rounded-xl border border-line bg-paper px-4 py-3"
                        >
                          <p className="text-sm font-semibold text-ink">{cluster.name}</p>
                          <p className="text-xs text-muted">
                            {cluster.start_at} - {cluster.end_at} · {cluster.photos.length} photos
                          </p>
                          <button
                            type="button"
                            className="mt-3 rounded-full border border-ink bg-ink px-4 py-2 text-xs font-semibold text-paper"
                            onClick={() => createChapter(cluster.name || 'New chapter', 0)}
                          >
                            Create chapter from cluster
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                  {clusterResults.length > 6 ? (
                    <p className="mt-3 text-xs font-semibold text-muted">
                      +{clusterResults.length - 6} more
                    </p>
                  ) : null}
                </section>
                <section className="rounded-2xl border border-line bg-paper px-6 py-6">
                  <div>
                    <p className="text-base font-semibold text-ink">Summary</p>
                    <p className="text-sm text-muted">High level readout for the run.</p>
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs uppercase tracking-[0.2em] text-muted">Clusters</p>
                      <p className="text-lg font-semibold text-ink">{clusterResults.length}</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-[0.2em] text-muted">Time range</p>
                      <p className="text-sm font-semibold text-ink">
                        {clusterResults.length > 0
                          ? `${clusterResults[0].start_at} - ${
                              clusterResults[clusterResults.length - 1].end_at
                            }`
                          : '—'}
                      </p>
                    </div>
                  </div>
                  {clusterJob && clusterJob.status !== 'completed' ? (
                    <p className="mt-4 text-xs text-muted">Job status: {clusterJob.status}</p>
                  ) : (
                    <p className="mt-4 text-xs text-muted">Last run ready to review.</p>
                  )}
                </section>
              </>
            ) : null}

            {activeStage === 'build' ? (
              <>
                <section className="rounded-2xl border border-line bg-paper px-6 py-6">
                  <div>
                    <p className="text-base font-semibold text-ink">Chapters</p>
                    <p className="text-sm text-muted">Organize the book into themes.</p>
                  </div>
                  <div className="mt-4 grid gap-3">
                    <input
                      type="text"
                      placeholder="Chapter name"
                      className="w-full rounded-xl border border-line bg-paper px-3 py-2 text-sm"
                      value={newChapterName}
                      onChange={(event) => setNewChapterName(event.target.value)}
                    />
                    <button
                      type="button"
                      className="rounded-full border border-ink bg-ink px-4 py-2 text-sm font-semibold text-paper"
                      onClick={handleCreateChapter}
                      disabled={!newChapterName.trim()}
                    >
                      Create chapter
                    </button>
                  </div>
                  {chapters.length === 0 ? (
                    <div className="mt-4 rounded-xl border border-line bg-paper px-4 py-6 text-center">
                      <p className="text-sm font-semibold text-ink">No chapters yet</p>
                      <p className="text-xs text-muted">Create the first chapter to begin.</p>
                    </div>
                  ) : (
                    <ul className="mt-4 space-y-3">
                      {chapters.map((chapter) => (
                        <li key={chapter.id}>
                          <button
                            type="button"
                            className={`flex w-full items-center justify-between rounded-xl border px-3 py-3 text-left transition ${
                              chapter.id === selectedChapterId
                                ? 'border-ink bg-paper'
                                : 'border-line bg-paper hover:border-ink/40'
                            }`}
                            onClick={() => setSelectedChapterId(chapter.id)}
                          >
                            <div>
                              <p className="text-sm font-semibold text-ink">{chapter.name}</p>
                              <p className="text-xs text-muted">
                                {chapter.page_count} pages · order {chapter.order_index}
                              </p>
                            </div>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>

                <section className="rounded-2xl border border-line bg-paper px-6 py-6">
                  <div>
                    <p className="text-base font-semibold text-ink">Pages</p>
                    <p className="text-sm text-muted">Select a page to edit.</p>
                  </div>
                  {selectedChapterId ? (
                    <>
                      <div className="mt-4 flex gap-3">
                        <input
                          type="number"
                          min="0"
                          placeholder="Set page count"
                          className="w-full rounded-xl border border-line bg-paper px-3 py-2 text-sm"
                          value={pageCountDraft}
                          onChange={(event) => setPageCountDraft(event.target.value)}
                        />
                        <button
                          type="button"
                          className="rounded-full border border-line bg-paper px-4 py-2 text-sm font-semibold text-ink"
                          onClick={handleUpdatePages}
                        >
                          Update
                        </button>
                      </div>
                      <p className="mt-3 text-xs text-muted">
                        Pages are auto-generated for the chapter and can be selected below.
                      </p>
                      {pages.length === 0 ? (
                        <div className="mt-4 rounded-xl border border-line bg-paper px-4 py-6 text-center">
                          <p className="text-sm font-semibold text-ink">No pages yet</p>
                          <p className="text-xs text-muted">Add pages to this chapter.</p>
                        </div>
                      ) : (
                        <div className="mt-4 grid grid-cols-2 gap-3">
                          {pages.map((page) => (
                            <button
                              key={page.id}
                              type="button"
                              className={`rounded-xl border px-3 py-3 text-sm font-semibold transition ${
                                page.id === selectedPageId
                                  ? 'border-ink bg-paper text-ink'
                                  : 'border-line bg-paper text-muted hover:border-ink/40'
                              }`}
                              onClick={() => setSelectedPageId(page.id)}
                            >
                              Page {page.page_index}
                            </button>
                          ))}
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="mt-4 rounded-xl border border-line bg-paper px-4 py-6 text-center">
                      <p className="text-sm font-semibold text-ink">Pick a chapter</p>
                      <p className="text-xs text-muted">Select a chapter to manage pages.</p>
                    </div>
                  )}
                </section>

                <section className="rounded-2xl border border-line bg-paper px-6 py-6">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="text-base font-semibold text-ink">Page layout</p>
                      <p className="text-sm text-muted">Add text or photo tiles.</p>
                    </div>
                    <button
                      type="button"
                      className="rounded-full border border-line bg-paper px-4 py-2 text-xs font-semibold text-ink"
                      onClick={handleAddTextItem}
                      disabled={!selectedPageId}
                    >
                      Add text
                    </button>
                  </div>
                  {selectedPageId ? (
                    <div className="mt-4 space-y-4">
                      <div
                        className="relative h-56 w-full overflow-hidden rounded-2xl border border-dashed border-line bg-paper"
                        onDrop={handleDropOnCanvas}
                        onDragOver={handleDragOverCanvas}
                      >
                        {pageItems.map((item) => (
                          <div
                            key={item.id}
                            className={`absolute flex items-center justify-center rounded-lg border text-[10px] ${
                              item.id === selectedLayoutItemId
                                ? 'border-ink bg-accentSoft text-ink'
                                : 'border-line bg-paper text-muted'
                            }`}
                            style={{
                              left: `${item.x * 100}%`,
                              top: `${item.y * 100}%`,
                              width: `${item.w * 100}%`,
                              height: `${item.h * 100}%`,
                              zIndex: item.z ?? 0,
                            }}
                            onClick={() => setSelectedLayoutItemId(item.id)}
                          >
                            <span>
                              {item.item_type === 'text'
                                ? item.text
                                : item.photo_path?.split('/').pop()}
                            </span>
                          </div>
                        ))}
                      </div>
                      <div className="flex items-center justify-between rounded-xl border border-line bg-paper px-3 py-2 text-xs">
                        <span className="font-semibold text-ink">Layout items</span>
                        <span className="text-muted">{layoutItemCount} elements placed</span>
                      </div>
                      {selectedLayoutItemId ? (
                        <div className="flex gap-3">
                          <button
                            type="button"
                            className="rounded-full border border-line bg-paper px-4 py-2 text-xs font-semibold text-ink"
                            onClick={() =>
                              handleUpdateItem(selectedLayoutItemId, {
                                w: Math.min(
                                  1,
                                  (pageItems.find((item) => item.id === selectedLayoutItemId)
                                    ?.w ?? 0.8) + 0.05,
                                ),
                                h: Math.min(
                                  1,
                                  (pageItems.find((item) => item.id === selectedLayoutItemId)
                                    ?.h ?? 0.6) + 0.05,
                                ),
                              })
                            }
                          >
                            Scale +
                          </button>
                          <button
                            type="button"
                            className="rounded-full border border-line bg-paper px-4 py-2 text-xs font-semibold text-ink"
                            onClick={() =>
                              handleUpdateItem(selectedLayoutItemId, {
                                w: Math.max(
                                  0.1,
                                  (pageItems.find((item) => item.id === selectedLayoutItemId)
                                    ?.w ?? 0.8) - 0.05,
                                ),
                                h: Math.max(
                                  0.1,
                                  (pageItems.find((item) => item.id === selectedLayoutItemId)
                                    ?.h ?? 0.6) - 0.05,
                                ),
                              })
                            }
                          >
                            Scale -
                          </button>
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <div className="mt-4 rounded-xl border border-line bg-paper px-4 py-6 text-center">
                      <p className="text-sm font-semibold text-ink">Select a page</p>
                      <p className="text-xs text-muted">Pick a page to edit layout.</p>
                    </div>
                  )}
                </section>

                <section className="rounded-2xl border border-line bg-paper px-6 py-6">
                  <div>
                    <p className="text-base font-semibold text-ink">Staging palette</p>
                    <p className="text-sm text-muted">Search and reuse photos.</p>
                  </div>
                  {buildPalette.length === 0 ? (
                    <p className="mt-4 text-xs text-muted">No thumbnails available yet.</p>
                  ) : (
                    <div className="mt-4 grid grid-cols-2 gap-3">
                      {[...buildPalette]
                        .sort((left, right) => {
                          if (layoutSort === 'score') {
                            return (right.score ?? 0) - (left.score ?? 0)
                          }
                          return (left.photo_path ?? '').localeCompare(right.photo_path ?? '')
                        })
                        .slice(0, 12)
                        .map((photo) => (
                          <button
                            key={photo.photo_path}
                            type="button"
                            className="rounded-xl border border-line bg-paper px-3 py-3 text-left text-xs text-muted"
                            draggable
                            onDragStart={() =>
                              setDragPayload({
                                type: 'palette',
                                photoPath: photo.photo_path,
                              })
                            }
                            onClick={() => handleAddPhotoItem(photo.photo_path)}
                          >
                            <span className="text-ink">
                              {photo.photo_path.split('/').pop()}
                            </span>
                          </button>
                        ))}
                    </div>
                  )}
                </section>
              </>
            ) : null}
            {activeStage === 'export' ? (
              <>
                <section className="rounded-2xl border border-line bg-paper px-6 py-6">
                  <div>
                    <p className="text-base font-semibold text-ink">Export package</p>
                    <p className="text-sm text-muted">Generate a shareable JSON bundle.</p>
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs uppercase tracking-[0.2em] text-muted">Chapters</p>
                      <p className="text-lg font-semibold text-ink">{chapters.length}</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-[0.2em] text-muted">Pages</p>
                      <p className="text-lg font-semibold text-ink">{pages.length}</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="mt-4 rounded-full border border-ink bg-ink px-4 py-2 text-sm font-semibold text-paper"
                    onClick={handleExport}
                    disabled={isExporting}
                  >
                    {isExporting ? 'Exporting...' : 'Export JSON'}
                  </button>
                </section>
                <section className="rounded-2xl border border-line bg-paper px-6 py-6">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-base font-semibold text-ink">Export preview</p>
                      <p className="text-sm text-muted">Latest JSON export snapshot.</p>
                    </div>
                    <button
                      type="button"
                      className="rounded-full border border-line bg-paper px-4 py-2 text-xs font-semibold text-ink"
                      onClick={handleDownloadExport}
                      disabled={!exportPayload}
                    >
                      Download
                    </button>
                  </div>
                  {exportPayload ? (
                    <div className="mt-4 max-h-60 overflow-auto rounded-xl border border-line bg-paper p-3 text-xs text-muted">
                      <pre className="whitespace-pre-wrap">
                        {JSON.stringify(exportPayload, null, 2)}
                      </pre>
                    </div>
                  ) : (
                    <div className="mt-4 rounded-xl border border-line bg-paper px-4 py-6 text-center">
                      <p className="text-sm font-semibold text-ink">No export yet</p>
                      <p className="text-xs text-muted">Run export to generate JSON.</p>
                    </div>
                  )}
                </section>
              </>
            ) : null}
          </div>
        </main>

        <aside
          className={`fixed right-6 top-6 z-40 h-[calc(100vh-48px)] w-[360px] max-w-[90vw] rounded-3xl border border-line bg-paper/95 p-6 shadow-soft transition-transform sm:right-0 sm:top-0 sm:h-screen sm:w-screen sm:rounded-none ${
            isDrawerOpen ? 'translate-x-0' : 'translate-x-[110%]'
          }`}
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-base font-semibold text-ink">Details</p>
              <p className="text-sm text-muted">Advanced controls and system status.</p>
            </div>
            <button
              type="button"
              className="rounded-full border border-line bg-paper px-4 py-2 text-xs font-semibold text-ink"
              onClick={() => setIsDrawerOpen(false)}
            >
              Close
            </button>
          </div>

          <div className="mt-6 max-h-[calc(100%-80px)] space-y-4 overflow-auto pr-1">
            <section className="rounded-2xl border border-line bg-paper px-4 py-4">
              <p className="text-xs uppercase tracking-[0.2em] text-muted">Stage controls</p>
              {activeStage === 'intake' ? (
                <div className="mt-3 grid gap-2">
                  <button
                    type="button"
                    className="rounded-full border border-line bg-paper px-3 py-2 text-xs font-semibold text-ink"
                    onClick={() => setFiles([])}
                    disabled={files.length === 0}
                  >
                    Clear sources
                  </button>
                  <button
                    type="button"
                    className="rounded-full border border-line bg-paper px-3 py-2 text-xs font-semibold text-ink"
                    onClick={() => folderInputRef.current?.click()}
                  >
                    Add folder
                  </button>
                </div>
              ) : null}
              {activeStage === 'clean' ? (
                <div className="mt-3 grid gap-2">
                  <button
                    type="button"
                    className="rounded-full border border-line bg-paper px-3 py-2 text-xs font-semibold text-ink"
                    onClick={triggerScore}
                    disabled={
                      thumbResults.length === 0 ||
                      ['running', 'queued'].includes(scoreJob?.status)
                    }
                  >
                    Score aesthetics
                  </button>
                  <button
                    type="button"
                    className="rounded-full border border-line bg-paper px-3 py-2 text-xs font-semibold text-ink"
                    onClick={() =>
                      setBestOverrides((prev) => {
                        if (!selectedStackId) {
                          return prev
                        }
                        const next = { ...prev }
                        delete next[selectedStackId]
                        return next
                      })
                    }
                    disabled={!selectedStackId}
                  >
                    Reset best shot
                  </button>
                </div>
              ) : null}
              {activeStage === 'organize' ? (
                <div className="mt-3 grid gap-2">
                  <button
                    type="button"
                    className="rounded-full border border-line bg-paper px-3 py-2 text-xs font-semibold text-ink"
                    onClick={triggerCluster}
                    disabled={
                      thumbResults.length === 0 ||
                      ['running', 'queued'].includes(clusterJob?.status)
                    }
                  >
                    Re-run clustering
                  </button>
                </div>
              ) : null}
              {activeStage === 'build' ? (
                <div className="mt-3 grid gap-3">
                  <label className="text-xs text-muted">
                    Source
                    <select
                      className="mt-1 w-full rounded-xl border border-line bg-paper px-3 py-2 text-xs"
                      value={layoutFilter}
                      onChange={(event) => setLayoutFilter(event.target.value)}
                    >
                      <option value="all">All</option>
                      <option value="clusters">Clusters</option>
                      <option value="duplicates">Best shots</option>
                    </select>
                  </label>
                  <label className="text-xs text-muted">
                    Sort
                    <select
                      className="mt-1 w-full rounded-xl border border-line bg-paper px-3 py-2 text-xs"
                      value={layoutSort}
                      onChange={(event) => setLayoutSort(event.target.value)}
                    >
                      <option value="name">Name</option>
                      <option value="score">Score</option>
                    </select>
                  </label>
                </div>
              ) : null}
              {activeStage === 'export' ? (
                <div className="mt-3 grid gap-2">
                  <button
                    type="button"
                    className="rounded-full border border-line bg-paper px-3 py-2 text-xs font-semibold text-ink"
                    onClick={handleDownloadExport}
                    disabled={!exportPayload}
                  >
                    Download JSON
                  </button>
                </div>
              ) : null}
            </section>

            <section className="rounded-2xl border border-line bg-paper px-4 py-4">
              <p className="text-xs uppercase tracking-[0.2em] text-muted">Job queue</p>
              <ul className="mt-3 space-y-3 text-xs">
                {[
                  { label: 'Thumbnails', stage: 'Clean', job: jobStatus },
                  { label: 'Clusters', stage: 'Organize', job: clusterJob },
                  { label: 'Duplicates', stage: 'Clean', job: dedupeJob },
                  { label: 'Scoring', stage: 'Clean', job: scoreJob },
                ].map((item) => (
                  <li
                    key={item.label}
                    className="flex items-center justify-between rounded-xl border border-line bg-paper px-3 py-2"
                  >
                    <div>
                      <p className="font-semibold text-ink">{item.label}</p>
                      <p className="text-muted">{item.stage}</p>
                    </div>
                    <span className="rounded-full bg-line px-2 py-1 text-xs font-semibold text-ink">
                      {item.job?.status ?? 'idle'}
                    </span>
                  </li>
                ))}
              </ul>
            </section>

            <section className="rounded-2xl border border-line bg-paper px-4 py-4">
              <p className="text-xs uppercase tracking-[0.2em] text-muted">Recent outcomes</p>
              <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
                <div>
                  <p className="text-muted">Sources</p>
                  <p className="font-semibold text-ink">{files.length}</p>
                </div>
                <div>
                  <p className="text-muted">Thumbnails</p>
                  <p className="font-semibold text-ink">{thumbResults.length}</p>
                </div>
                <div>
                  <p className="text-muted">Scores</p>
                  <p className="font-semibold text-ink">{scoreResults.length}</p>
                </div>
                <div>
                  <p className="text-muted">Clusters</p>
                  <p className="font-semibold text-ink">{clusterResults.length}</p>
                </div>
                <div>
                  <p className="text-muted">Stacks</p>
                  <p className="font-semibold text-ink">{duplicateResults.length}</p>
                </div>
              </div>
            </section>

            <section className="rounded-2xl border border-line bg-paper px-4 py-4">
              <p className="text-xs uppercase tracking-[0.2em] text-muted">System health</p>
              {errorMessage ? (
                <div className="mt-3 rounded-xl border border-accent/30 bg-accentSoft/60 px-3 py-3 text-xs text-accent">
                  <p className="font-semibold">Action needed</p>
                  <p>{errorMessage}</p>
                </div>
              ) : (
                <div className="mt-3 grid gap-2 text-xs text-muted">
                  <div className="flex items-center justify-between">
                    <span>Thumbnail API</span>
                    <span className="font-semibold text-ink">Online</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>Cluster worker</span>
                    <span className="font-semibold text-ink">Standing by</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>Dedupe worker</span>
                    <span className="font-semibold text-ink">Standing by</span>
                  </div>
                </div>
              )}
            </section>
          </div>
        </aside>
      </div>
    </div>
  )
}

export default App
