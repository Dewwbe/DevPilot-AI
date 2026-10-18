FROM node:20-alpine AS build
WORKDIR /src
COPY package*.json ./
RUN npm ci || npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /src/dist /usr/share/nginx/html
ENV API_UPSTREAM=api:8000
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 8080
