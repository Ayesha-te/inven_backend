release: python manage.py migrate --noinput --settings=ims_backend.settings_production
web: gunicorn ims_backend.wsgi_production:application --bind 0.0.0.0:$PORT
worker: python manage.py qcluster --settings=ims_backend.settings_production
