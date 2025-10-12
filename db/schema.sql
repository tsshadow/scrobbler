-- MariaDB 11 schema for the analyzer/scrobbler stack
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE IF NOT EXISTS user_account (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  username      VARCHAR(190) NOT NULL,
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_user_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS artist (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name          VARCHAR(512) NOT NULL,
  normalized    VARCHAR(512) NOT NULL,
  mbid          CHAR(36) NULL,
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_artist_name (name),
  KEY idx_artist_normalized (normalized),
  KEY idx_artist_mbid (mbid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS artist_alias (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  artist_id     BIGINT UNSIGNED NOT NULL,
  alias         VARCHAR(512) NOT NULL,
  normalized    VARCHAR(512) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_artist_alias (alias),
  KEY idx_artist_alias_normalized (normalized),
  CONSTRAINT fk_alias_artist FOREIGN KEY (artist_id) REFERENCES artist(id)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS genre (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name          VARCHAR(190) NOT NULL,
  normalized    VARCHAR(190) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_genre_name (name),
  KEY idx_genre_normalized (normalized)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS label (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name          VARCHAR(255) NOT NULL,
  normalized    VARCHAR(255) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_label_name (name),
  KEY idx_label_normalized (normalized)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS album (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  title         VARCHAR(512) NOT NULL,
  normalized    VARCHAR(512) NOT NULL,
  label_id      BIGINT UNSIGNED NULL,
  release_date  DATE NULL,
  mbid          CHAR(36) NULL,
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_album_normalized (normalized),
  KEY idx_album_mbid (mbid),
  CONSTRAINT fk_album_label FOREIGN KEY (label_id) REFERENCES label(id)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS track (
  id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  title             VARCHAR(512) NOT NULL,
  normalized        VARCHAR(512) NOT NULL,
  album_id          BIGINT UNSIGNED NULL,
  duration_ms       INT UNSIGNED NULL,
  isrc              CHAR(12) NULL,
  fingerprint_hash  VARCHAR(64) NULL,
  track_uid         CHAR(40) NOT NULL,
  external_ids      JSON NULL,
  created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_track_uid (track_uid),
  KEY idx_track_album (album_id),
  KEY idx_track_title_norm (normalized),
  KEY idx_track_fingerprint (fingerprint_hash),
  CONSTRAINT fk_track_album FOREIGN KEY (album_id) REFERENCES album(id)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS track_artist (
  track_id     BIGINT UNSIGNED NOT NULL,
  artist_id    BIGINT UNSIGNED NOT NULL,
  role         ENUM('primary','featuring','remixer','producer') NOT NULL DEFAULT 'primary',
  position_no  SMALLINT UNSIGNED NOT NULL DEFAULT 1,
  PRIMARY KEY (track_id, artist_id, role, position_no),
  KEY idx_ta_artist (artist_id),
  CONSTRAINT fk_ta_track FOREIGN KEY (track_id) REFERENCES track(id)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_ta_artist FOREIGN KEY (artist_id) REFERENCES artist(id)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS track_genre (
  track_id     BIGINT UNSIGNED NOT NULL,
  genre_id     BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY (track_id, genre_id),
  KEY idx_tg_genre (genre_id),
  CONSTRAINT fk_tg_track FOREIGN KEY (track_id) REFERENCES track(id)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_tg_genre FOREIGN KEY (genre_id) REFERENCES genre(id)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS listen (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id        BIGINT UNSIGNED NOT NULL,
  track_id       BIGINT UNSIGNED NULL,
  played_at      TIMESTAMP NOT NULL,
  source         ENUM('LMS','ListenBrainz','YouTube','SoundCloud','Other') NOT NULL DEFAULT 'ListenBrainz',
  device         VARCHAR(190) NULL,
  context_json   JSON NULL,
  raw_title      VARCHAR(512) NOT NULL,
  raw_artists    JSON NOT NULL,
  raw_duration_ms INT UNSIGNED NULL,
  raw_album      VARCHAR(512) NULL,
  raw_mbids      JSON NULL,
  created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_listen_user_time (user_id, played_at),
  KEY idx_listen_track_time (track_id, played_at),
  KEY idx_listen_source (source),
  CONSTRAINT fk_listen_user FOREIGN KEY (user_id) REFERENCES user_account(id)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT fk_listen_track FOREIGN KEY (track_id) REFERENCES track(id)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS rating (
  user_id     BIGINT UNSIGNED NOT NULL,
  track_id    BIGINT UNSIGNED NOT NULL,
  stars       TINYINT UNSIGNED NOT NULL,
  rated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, track_id),
  CONSTRAINT chk_rating_range CHECK (stars BETWEEN 1 AND 5),
  CONSTRAINT fk_rating_user FOREIGN KEY (user_id) REFERENCES user_account(id)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_rating_track FOREIGN KEY (track_id) REFERENCES track(id)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS track_candidate (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  listen_id   BIGINT UNSIGNED NOT NULL,
  track_id    BIGINT UNSIGNED NOT NULL,
  score       INT NOT NULL,
  reason_json JSON NULL,
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_tc_listen (listen_id),
  KEY idx_tc_track (track_id),
  CONSTRAINT fk_tc_listen FOREIGN KEY (listen_id) REFERENCES listen(id)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_tc_track FOREIGN KEY (track_id) REFERENCES track(id)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET FOREIGN_KEY_CHECKS = 1;
