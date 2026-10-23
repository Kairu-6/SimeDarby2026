# Cleaner alerts

When either compartment reaches 90%, the API stores a collection task and an in-app notification for cleaners assigned to that township. Duplicate high readings do not create duplicate open tasks. An accepted task can be marked cleared, which resolves that task and resets only its compartment. The next genuine high sensor reading can create a fresh alert.

The app polls while open. On native devices it can show a local foreground notification after permission is granted. Browser users receive the notification list, queue update and in-app message; browser Web Push is not implemented.

## Native background push

The software path is implemented, but project credentials must come from your Expo account:

1. Follow [Expo's push setup](https://docs.expo.dev/push-notifications/push-notifications-setup/) to configure an EAS project and Android FCM/iOS APNs credentials. Use a native preview/development build with push support.
2. Supply the project's UUID in app config via EAS setup or `EXPO_PUBLIC_EAS_PROJECT_ID`. Rebuild the native app after changing native notification configuration.
3. In `backend/.env`, set `PUSH_NOTIFICATIONS_ENABLED=true` and restart the API. The server needs outbound HTTPS access to the Expo Push Service.
4. Sign in as a cleaner on that native build and grant notifications. The app gets an Expo push token and registers it with authenticated `POST /api/push-tokens`.
5. Send a full sensor reading for the cleaner's assigned township. The same database transaction creates the task, notification and durable push-outbox row. The API's background worker submits pending rows and retries transient errors with exponential backoff, up to five attempts. Invalid/unregistered tokens are removed.

Provider submission is stored as `submitted`, not `delivered`. The implementation does not poll Expo push receipts; add receipt tracking for a live deployment. See [Expo's sending guide](https://docs.expo.dev/push-notifications/sending-notifications/). The queue remains useful without push configuration, so you can demonstrate alerts without a cloud account.

Tests verify outbox creation and submission using a mocked provider. No real remote notification was sent during development.
