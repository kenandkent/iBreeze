use ibreeze_desktop_core::sidecar::SidecarSupervisor;

#[tokio::test]
async fn supervisor_initial_state() {
    let supervisor = SidecarSupervisor::new();
    assert!(
        !supervisor.is_running().await,
        "supervisor must start not running"
    );
    assert_eq!(supervisor.restart_count().await, 0, "no restarts initially");
}

#[tokio::test]
async fn stop_empty_supervisor_returns_false() {
    let supervisor = SidecarSupervisor::new();
    let result = supervisor
        .stop()
        .await
        .expect("stop empty supervisor must succeed");
    assert!(!result, "stop on empty supervisor must return false");
}

#[tokio::test]
async fn restart_tracker_tracks_restarts() {
    let supervisor = SidecarSupervisor::new();
    assert!(!supervisor.is_throttled().await, "not throttled initially");
    supervisor.record_restart().await;
    supervisor.record_restart().await;
    supervisor.record_restart().await;
    assert!(
        supervisor.is_throttled().await,
        "throttled after 3 restarts"
    );
}
