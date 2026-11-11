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

## 6. Interests: tags to hear about

A user can follow tags (`tag_subscriptions`, lowercased, up to 30). When a course carrying one of
them is published for the first time, each follower gets one `course_new` notification
(`{listing_id, title, tag}`); not the author, not who already has the course, not across a block.
A new version of a course tells only the people who have it (`course_update`).

```
GET    /api/v1/interests          # {tags, suggestions}: suggestions are tags of published courses
PUT    /api/v1/interests          # {tag}
DELETE /api/v1/interests?tag=
```

## 7. Reports to the administrator

Anyone can report a person, a message they received or a review, with an optional reason
(`reports`; reporting the same thing again updates it). The report keeps a copy of what was
reported (the name, that one message, that one review): the administrator sees that and nothing
else of anyone's conversations. In Administration → Reports the administrator marks it resolved,
removes the review or suspends the account.

```
POST /api/v1/reports                          # {kind: user|message|review, target_id, reason}
GET  /api/v1/admin/reports                    # open ones first
POST /api/v1/admin/reports/{id}/resolve | /reopen
```

## 8. Privacy notice and deleting the account

`/privacy` in the app (also reachable signed out) says what is stored, who sees it, what goes to
the AI service and how to delete everything. `POST /api/v1/auth/delete-account {password}`
deletes the signed-in account with everything it owns (the same as an administrator deleting
it); the only administrator can't (409 `last_admin`).

## 9. Not built yet

- No rate limits on announcements; friend requests, messages, searches and reports are limited
  per account per hour.
- No push notifications (the installed web app polls while open).
