# Community: leaderboards, friends, messages, notifications

Code: `backend/app/services/community.py`, `chat.py`, `notifications.py`,
`backend/app/models/community.py`, `web/src/features/community/`, `web/src/features/notifications/`.

## 1. Opt-in

Nothing here is on by default. A user who hasn't turned on `community_visible` (and chosen a
display name) appears on no leaderboard, can't be found, can't be asked to be a friend and has no
profile page. Other people only ever see the display name, XP and streak; never the email.

## 2. Leaderboards

Rankings come from the XP ledger (`xp_awards`), over UTC calendar windows so everyone is compared
on the same clock: `day` (since 00:00 UTC), `week` (since Monday), `month` (since the 1st), `all`.
Scope is `everyone` or `friends`. A course from the marketplace also has its own leaderboard
(everyone who has that course).

```
GET /api/v1/community/leaderboard?period&scope
GET /api/v1/community/users/{user_id}          # profile: name, XP, streak, friends, relation, blocked
GET /api/v1/community/people?q                 # search by display name (2+ letters, 20 results)
```

## 3. Friends

Friendship is mutual and needs an answer (the one-way "follow" of the first version is gone;
migration `5e0f2b7a9c43` turned mutual follows into friendships and one-way follows into pending
requests).

`relation` between the viewer and someone else is one of `none`, `request_sent`,
`request_received`, `friends`. One row per pair of people (`friendships.pair_key` unique), so two
crossing requests can't both exist: asking someone who already asked you accepts their request.

```
PUT    /api/v1/community/users/{user_id}/friend   # ask, or accept their request
DELETE /api/v1/community/users/{user_id}/friend   # cancel my request, decline theirs, or remove the friend
GET    /api/v1/community/friends
GET    /api/v1/community/friend-requests          # {incoming, outgoing}
PUT    /api/v1/community/users/{user_id}/block    # also ends the friendship and any request
DELETE /api/v1/community/users/{user_id}/block
GET    /api/v1/community/blocked
```

Declining, cancelling and removing all delete the row: either person may ask again later. A block
is one-sided and silent: the blocked person isn't told, and neither finds the other in search,
leaderboards or profiles. Blocked people are listed in Settings, where they can be unblocked.

## 4. Messages

Private, plain-text messages between two friends. Ending the friendship or blocking stops new
messages and leaves the history readable. There is no push channel on the small server this runs
on: the app polls (an open conversation every 5 s, the list every 15 s, the unread counts every 30 s).

```
GET  /api/v1/chats              # every chat, most recent first, then friends never written to
GET  /api/v1/chats/{user_id}    # a page of 50 messages (?before= for older); marks theirs as read
POST /api/v1/chats/{user_id}    # {text}
```

## 5. Notifications

Written by the service where the thing happens, in the same transaction; read by the bell in the
top bar. Kinds: `friend_request`, `friend_accepted`, `course_update`, `course_announcement`,
`course_review`, `review_reply`, `course_sold` (their `data` is listed at the top of
`services/notifications.py`). The interface writes the sentence from the kind, in the user's
language; a kind it doesn't know shows a generic line.

```
GET  /api/v1/inbox                 # {notifications, messages, friend_requests}: the unread counts for the badges
GET  /api/v1/notifications         # the last 50
POST /api/v1/notifications/read    # {ids?}: these, or all
```

Course updates and authors' announcements are also emailed when the server can send email and the
user left "Email me…" on in Settings (`users.email_updates`, on by default).

## 6. Not built yet

- No rate limits on friend requests, messages or announcements (fine while registration is by
  invitation; needed before opening it).
- No reporting of a person or a message to the administrator; blocking is the only tool.
- No push notifications (the installed web app polls while open).
