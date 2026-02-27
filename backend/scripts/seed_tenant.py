"""
Seed script — Create your development tenant.
Run this once after setting up the DB.

Usage:
    python -m scripts.seed_dev_tenant
"""

import asyncio
from uuid import uuid4

from sqlalchemy import select

from app.config import get_settings
from app.core.database import async_session
from app.models.tenant import Tenant

settings = get_settings()


async def seed():
    async with async_session() as db:
        # Check if dev tenant already exists
        result = await db.execute(
            select(Tenant).where(Tenant.slug == "dev")
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"✅ Dev tenant already exists: {existing.name}")
            print(f"   ID: {existing.id}")
            print(f"   Phone Number ID: {existing.wa_phone_number_id}")

            # Update phone_number_id if it changed
            if existing.wa_phone_number_id != settings.WHATSAPP_PHONE_NUMBER_ID:
                existing.wa_phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
                await db.commit()
                print(f"   ↳ Updated phone_number_id to: {settings.WHATSAPP_PHONE_NUMBER_ID}")

            return

        # Create dev tenant
        tenant = Tenant(
            id=uuid4(),
            name="Dev Clinic (Test)",
            slug="dev",
            wa_phone_number_id=settings.WHATSAPP_PHONE_NUMBER_ID,
            plan="pro",
            # is_active=True,  # This column does not exist in your Tenant model currently
        )
        db.add(tenant)
        await db.commit()

        print(f"🎉 Dev tenant created!")
        print(f"   ID: {tenant.id}")
        print(f"   Name: {tenant.name}")
        print(f"   Phone Number ID: {tenant.wa_phone_number_id}")
        print(f"   Plan: {tenant.plan}")


if __name__ == "__main__":
    asyncio.run(seed())