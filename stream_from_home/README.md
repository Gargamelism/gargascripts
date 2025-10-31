# Stream From Home

Music streaming server using Gonic and Pinggy.

## Setup

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and set your paths and credentials:
   - Update all `GONIC_*` paths to point to your music directories
   - Add your Pinggy credential

3. Start the services:
   ```bash
   docker-compose up -d
   ```

4. Access Gonic at `http://localhost:4747`
