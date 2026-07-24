from interface.api import router

print("Routes in interface.api.router:")
for route in router.routes:
    print(f"  {route.path} ({route.name})")
