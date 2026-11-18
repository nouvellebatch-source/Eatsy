# syntax=docker/dockerfile:1
# La URL de la API se incorpora al bundle del panel en el momento de construirlo.
FROM node:22-alpine AS build
WORKDIR /app

COPY panel/package.json ./
RUN npm install

COPY panel/ ./
ARG VITE_EATSY_API_URL=https://eatsy-1.onrender.com
ENV VITE_EATSY_API_URL=$VITE_EATSY_API_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
