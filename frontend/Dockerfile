FROM node:20-slim

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

# node:20-slim already ships a non-root "node" user -- use it rather
# than running as root (Phase 6 audit finding, same reasoning as the
# backend Dockerfile).
RUN chown -R node:node /app
USER node

EXPOSE 3000

CMD ["npm", "run", "dev"]
