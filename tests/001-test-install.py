import amulet
d = amulet.Deployment()
d.add('errbot')
d.configure('errbot', {'version': '3.2.2'})
d.setup()
d.sentry.wait()
print(d.sentry['errbot/0'].run('/srv/errbot/venv/bin/errbot'))
