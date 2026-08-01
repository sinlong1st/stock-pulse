"""Native push notifications for the mobile app (Expo Push API → FCM/APNs).

Additive and isolated: token storage + a send helper. Single-user MVP — the
token store becomes a per-user table in the multi-tenant phase.
"""
