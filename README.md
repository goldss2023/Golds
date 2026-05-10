# Midas Markets

Production-ready Next.js App Router site for a premium AI trading brand with accounts, automated crypto checkout, Supabase storage, manual Telegram VIP management, products, and an admin console.

## Stack

- Next.js App Router, TypeScript, Tailwind CSS
- Framer Motion for cinematic motion
- Supabase Postgres and Storage
- NOWPayments invoices and IPN webhooks
- Manual Telegram group approval after confirmed payment
- Netlify-ready deployment

## Local Setup

1. Install dependencies:

```bash
npm install
```

2. Copy `.env.example` to `.env.local` and fill values:

```bash
cp .env.example .env.local
```

3. Run the Supabase migration in `supabase/migrations/001_initial_schema.sql`.

4. Start the site:

```bash
npm run dev
```

## Netlify

Build command: `npm run build`

Publish directory: `.next`

Set all variables from `.env.example` in Netlify before production use.