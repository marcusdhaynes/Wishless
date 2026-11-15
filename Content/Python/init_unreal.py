"""Auto-discovered startup script by Unreal Python Editor Script Plugin."""
try:
    import wishless_bridge
    wishless_bridge.start()
except Exception as exc:
    import unreal
    unreal.log_error(f"[WishlessBridge] Startup failed: {exc}")
