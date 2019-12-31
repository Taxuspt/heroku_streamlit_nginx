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
