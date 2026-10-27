.method public surfaceDestroyed()V
    .locals 3
    const/4 v2, 0x0
    iget-object v1, p0, Lcom/apportable/gl/GLSurfaceView;->mLock:Ljava/lang/Object;
    monitor-enter v1
    :zb_start
    const/4 v0, 0x0
    iput-boolean v0, p0, Lcom/apportable/gl/GLSurfaceView;->mHasSurface:Z
    invoke-virtual {v1}, Ljava/lang/Object;->notifyAll()V
    invoke-static {}, Lcom/zettabridge/compat/SurfaceWait;->isOwner()Z
    move-result v0
    if-eqz v0, :zb_loop
    # A callback dispatched by the owner cannot wait for that same owner.
    # Release the old EGL window before acknowledging surface destruction.
    invoke-virtual {p0}, Lcom/apportable/gl/GLSurfaceView;->stopEglSurfaceLocked()V
    const/4 v0, 0x1
    iput-boolean v0, p0, Lcom/apportable/gl/GLSurfaceView;->mWaitingForSurface:Z
    invoke-virtual {v1}, Ljava/lang/Object;->notifyAll()V
    goto :zb_done
    :zb_loop
    iget-boolean v0, p0, Lcom/apportable/gl/GLSurfaceView;->mWaitingForSurface:Z
    if-nez v0, :zb_done
    iget-boolean v0, p0, Lcom/apportable/gl/GLSurfaceView;->mExited:Z
    if-nez v0, :zb_done
    :zb_wait_start
    invoke-virtual {v1}, Ljava/lang/Object;->wait()V
    :zb_wait_end
    .catch Ljava/lang/InterruptedException; {:zb_wait_start .. :zb_wait_end} :zb_interrupted
    goto :zb_loop
    :zb_interrupted
    move-exception v0
    const/4 v2, 0x1
    goto :zb_loop
    :zb_done
    monitor-exit v1
    :zb_end
    .catchall {:zb_start .. :zb_end} :zb_failure
    if-eqz v2, :zb_return
    invoke-static {}, Ljava/lang/Thread;->currentThread()Ljava/lang/Thread;
    move-result-object v0
    invoke-virtual {v0}, Ljava/lang/Thread;->interrupt()V
    :zb_return
    return-void
    :zb_failure
    move-exception v0
    monitor-exit v1
    throw v0
.end method
