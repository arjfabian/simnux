FROM nginx:alpine

COPY . /usr/share/nginx/html

ARG BACKEND_URL

RUN printf 'window.SIMNUX_CONFIG = {\n    BACKEND_URL: "%s",\n};\n' \
    "$BACKEND_URL" \
    > /usr/share/nginx/html/config.js
