# Host Streamlit on Heroku with Nginx

Created By: Alexandre Domingues
Last Edited: Dec 31, 2019 11:45 AM
Tags: Heroku, Nginx, Streamlit

# Streamlit app hosted on Heroku

## Setup your environment

`mkdir my_project`

`cd my_project`

Since we're hosting on Heroku it's recommended that we create a dedicated virtual environment  

`virtualenv .venv`

`source .venv/bin/activate`

At this stage the only dependency is streamlit itself

`pip install streamlit`

Create a streamlit test app. And save it on app.py

    # Contents of app.py

    import streamlit as st

    st.write('This is a streamlit app')

Test your streamlit application locally

`streamlit run app.py`

If all goes well you should see a page with a message

## Setup the Heroku app

Create a Procfile that will launch your app don't forget to set the Port and disable CORs (cross origin requests).

    # Contents of Procfile
    web: streamlit run --server.enableCORS false --server.port $PORT app.py

Freeze your requirements, Heroku needs this to know how to initialise the environment.

`pip freeze > requirements.txt`

Now, create the heroku app, add it to git and push everything

    heroku create

    git init
    git add .
    git commit -m "Repo Init"

    git push heroku master

After the deployment finished successfully you can visit your app with `heroku open`.

# Setting up the nginx proxy

## Nginx buildpack

Start by adding the nginx buildpack to your Heroku app

`heroku buildpacks:add [https://github.com/heroku/heroku-buildpack-nginx](https://github.com/heroku/heroku-buildpack-nginx)`

You should see

    Buildpack added. Next release on <your app> will use:
      1. heroku/python
      2. https://github.com/heroku/heroku-buildpack-nginx
    Run git push heroku master to create a new release using these buildpacks.

## Changes to the Procfile

The `Procfile` needs a couple of changes:

- Start the nginx server instead of streamlit:
`bin/start-nginx streamlit run --server.enableCORS false --server.port 8501 [app.py](http://app.py/)`
The port on streamlit is set to the default (8501), this port will not be exposed by Heroku but will be accessible by nginx.
- By default, nginx assumes that the "private" webserver is ready when `/tmp/app-initialized` is created. Streamlit uses Tornado but (afaik) there's no way yo capture it's ready state from Streamlit. A (possible flawled) workaround is to wait a few seconds and then manually create this file. e.g. `sleep 10 && touch '/tmp/app-initialized'`

The Procfile becomes

    # Content of Procfile
    web: sleep 10 && touch '/tmp/app-initialized' & bin/start-nginx streamlit run --server.enableCORS false --server.port 8501 app.py

## Nginx configuration

A custom configuration can be passed to nginx by creating a `nginx.conf.erb` inside the `/config` folder.

The content of this file is:

    # Content of /config/nginx.conf.erb

    daemon off;
    #Heroku dynos have at least 4 cores.
    worker_processes <%= ENV['NGINX_WORKERS'] || 4 %>;

    events {
       use epoll;
       accept_mutex on;
       worker_connections <%= ENV['NGINX_WORKER_CONNECTIONS'] || 1024 %>;
    }

    http {
        map $http_upgrade $connection_upgrade {
            default upgrade;
            '' close;
        }

        gzip on;
        gzip_comp_level 2;
        gzip_min_length 512;

       server_tokens off;

       log_format l2met 'measure#nginx.service=$request_time request_id=$http_x_request_id';
       access_log <%= ENV['NGINX_ACCESS_LOG_PATH'] || 'logs/nginx/access.log' %> l2met;
       error_log <%= ENV['NGINX_ERROR_LOG_PATH'] || 'logs/nginx/error.log' %>;

       include mime.types;
       default_type application/octet-stream;
       sendfile on;

       #Must read the body in 5 seconds.
       client_body_timeout 5;

       server {
          listen <%= ENV["PORT"] %>;
          server_name localhost;
          keepalive_timeout 5;

          location / {
              proxy_pass http://127.0.0.1:8501/;
          }
          location ^~ /static {
              proxy_pass http://127.0.0.1:8501/static/;
          }
          location ^~ /healthz {
              proxy_pass http://127.0.0.1:8501/healthz;
          }
          location ^~ /vendor {
              proxy_pass http://127.0.0.1:8501/vendor;
          }
          location /stream {
              proxy_pass http://127.0.0.1:8501/stream;
              proxy_http_version 1.1;
              proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
              proxy_set_header Host $host;
              proxy_set_header Upgrade $http_upgrade;
              proxy_set_header Connection "upgrade";
              proxy_read_timeout 86400;
          }
       }
    }

# Adding support to multiple streamlit apps

I considered two different approaches to host multiple streamlit apps on the same server:

- Start a single process (`streamlit run app1`) for each app. This implies starting multiple tornado servers and dealing with the routing with nginx.
- Start a main streamlit app and import other apps as modules from within the main app.

There are probably a couple of caveats but I'll go with option 2.

The main app will list all modules from `apps.json` that have a `run` method *(this is potentially unsafe)* and show an option to run each script/app.

    # Contents of app.py
    import json
    import streamlit as st

    def import_module(name):
        mod = __import__(name)
        components = name.split('.')
        for comp in components[1:]:
            mod = getattr(mod, comp)
        return mod

    st.sidebar.markdown('Select an app from the dropdown list')

    with open('apps.json','r') as f:
        apps = {a['name']:a['module'] for a in json.load(f)}

    app_names = []
    for name, module in apps.items():
        if hasattr(import_module(module), 'run'):
            app_names.append(name)

    run_app = st.sidebar.selectbox("Select the app", app_names)

    submit = st.sidebar.button('Run selected app')
    if submit:
        import_module(apps[run_app]).run()

The apps are normal streamlit scripts that run via a `run` method.

    # Example of streamlit app, stored under scripts/app_something.py
    import streamlit as st

    def run():
        st.write('I am a secondary streamlit app')

    if __name__ == '__main__':
        run()

# Adding authentication to nginx

Create a file with your encrypted password with:

`htpasswd -c .htpasswd <your username>`

Add the resulting file to the root of the project and edit the `/config/nginx.conf.erb` file blocking the locations that you want to protect. E.g.

    # The path to .htpasswd needs to be absolute (assume Heroku's filesystem)

    location / {
              auth_basic           "closed site";
              auth_basic_user_file /app/.htpasswd;
              proxy_pass http://127.0.0.1:8501/;
          }
