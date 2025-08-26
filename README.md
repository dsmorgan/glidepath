# Glidepath

This repository provides a minimal [Django](https://www.djangoproject.com/) application.
It includes a `Hello, World!` view and is configured to run inside Docker using
`docker-compose`.

## Quickstart

Build the image and start the development server:

```bash
docker-compose up --build
```

Then visit <http://localhost:8000/> to see the greeting.

## Running tests

```bash
docker-compose run --rm web python manage.py test
```
