-- Add integrity constraints and query indexes after COPY has completed.
SET statement_timeout = 0;

ALTER TABLE work_creator ADD PRIMARY KEY (id);
ALTER TABLE work_creator ADD CONSTRAINT uk_work_creator_uuid UNIQUE (uuid);
ALTER TABLE quillent_work ADD PRIMARY KEY (id);
ALTER TABLE quillent_work ADD CONSTRAINT uk_quillent_work_uuid UNIQUE (uuid);
ALTER TABLE work_editions ADD PRIMARY KEY (id);
ALTER TABLE work_editions ADD CONSTRAINT uk_work_editions_uuid UNIQUE (uuid);
ALTER TABLE search_tag ADD PRIMARY KEY (id);
ALTER TABLE search_tag ADD CONSTRAINT uk_search_tag_name UNIQUE (tag_name);

ALTER TABLE author_external_identifier ADD PRIMARY KEY (provider, external_id);
ALTER TABLE work_external_identifier ADD PRIMARY KEY (provider, external_id);
ALTER TABLE edition_external_identifier ADD PRIMARY KEY (provider, external_id);
ALTER TABLE work_creators ADD PRIMARY KEY (work_id, creator_id);
ALTER TABLE edition_creators ADD PRIMARY KEY (edition_id, creator_id);
ALTER TABLE work_tags ADD PRIMARY KEY (work_id, tag_id);
ALTER TABLE author_tag_profile ADD PRIMARY KEY (author_id, tag_id);
ALTER TABLE author_profile_state ADD PRIMARY KEY (author_id);
ALTER TABLE similar_author ADD PRIMARY KEY (author_id, similar_author_id);
ALTER TABLE similar_author ADD CONSTRAINT uk_similar_author_rank UNIQUE (author_id, rank);
ALTER TABLE author_profile_refresh_queue ADD PRIMARY KEY (author_id);

ALTER TABLE author_external_identifier ADD FOREIGN KEY (author_id) REFERENCES work_creator(id) ON DELETE CASCADE;
ALTER TABLE author_alternate_name ADD FOREIGN KEY (author_id) REFERENCES work_creator(id) ON DELETE CASCADE;
ALTER TABLE author_external_link ADD FOREIGN KEY (author_id) REFERENCES work_creator(id) ON DELETE CASCADE;
ALTER TABLE work_external_identifier ADD FOREIGN KEY (work_id) REFERENCES quillent_work(id) ON DELETE CASCADE;
ALTER TABLE work_cover ADD FOREIGN KEY (work_id) REFERENCES quillent_work(id) ON DELETE CASCADE;
ALTER TABLE work_editions ADD FOREIGN KEY (work_id) REFERENCES quillent_work(id) ON DELETE CASCADE;
ALTER TABLE quillent_work ADD FOREIGN KEY (featured_edition_fk) REFERENCES work_editions(id);
ALTER TABLE edition_external_identifier ADD FOREIGN KEY (edition_id) REFERENCES work_editions(id) ON DELETE CASCADE;
ALTER TABLE edition_identifier ADD FOREIGN KEY (edition_id) REFERENCES work_editions(id) ON DELETE CASCADE;
ALTER TABLE edition_publisher ADD FOREIGN KEY (edition_id) REFERENCES work_editions(id) ON DELETE CASCADE;
ALTER TABLE edition_cover ADD FOREIGN KEY (edition_id) REFERENCES work_editions(id) ON DELETE CASCADE;
ALTER TABLE edition_language ADD FOREIGN KEY (edition_id) REFERENCES work_editions(id) ON DELETE CASCADE;
ALTER TABLE work_creators ADD FOREIGN KEY (work_id) REFERENCES quillent_work(id) ON DELETE CASCADE;
ALTER TABLE work_creators ADD FOREIGN KEY (creator_id) REFERENCES work_creator(id) ON DELETE CASCADE;
ALTER TABLE edition_creators ADD FOREIGN KEY (edition_id) REFERENCES work_editions(id) ON DELETE CASCADE;
ALTER TABLE edition_creators ADD FOREIGN KEY (creator_id) REFERENCES work_creator(id) ON DELETE CASCADE;
ALTER TABLE work_tags ADD FOREIGN KEY (work_id) REFERENCES quillent_work(id) ON DELETE CASCADE;
ALTER TABLE work_tags ADD FOREIGN KEY (tag_id) REFERENCES search_tag(id) ON DELETE CASCADE;
ALTER TABLE author_tag_profile ADD FOREIGN KEY (author_id) REFERENCES work_creator(id) ON DELETE CASCADE;
ALTER TABLE author_tag_profile ADD FOREIGN KEY (tag_id) REFERENCES search_tag(id) ON DELETE CASCADE;
ALTER TABLE author_profile_state ADD FOREIGN KEY (author_id) REFERENCES work_creator(id) ON DELETE CASCADE;
ALTER TABLE similar_author ADD FOREIGN KEY (author_id) REFERENCES work_creator(id) ON DELETE CASCADE;
ALTER TABLE similar_author ADD FOREIGN KEY (similar_author_id) REFERENCES work_creator(id) ON DELETE CASCADE;
ALTER TABLE author_profile_refresh_queue ADD FOREIGN KEY (author_id) REFERENCES work_creator(id) ON DELETE CASCADE;

CREATE INDEX idx_author_external_identifier_author ON author_external_identifier(author_id);
CREATE INDEX idx_work_external_identifier_work ON work_external_identifier(work_id);
CREATE INDEX idx_edition_external_identifier_edition ON edition_external_identifier(edition_id);
CREATE INDEX idx_work_creators_creator_work ON work_creators(creator_id, work_id);
CREATE INDEX idx_work_tags_tag_work ON work_tags(tag_id, work_id);
CREATE INDEX idx_work_editions_work ON work_editions(work_id);
CREATE INDEX idx_work_editions_isbn10 ON work_editions(isbn_ten) WHERE isbn_ten IS NOT NULL;
CREATE INDEX idx_work_editions_isbn13 ON work_editions(isbn_thirteen) WHERE isbn_thirteen IS NOT NULL;
CREATE INDEX idx_quillent_work_publication_date ON quillent_work(publication_date_epoch) WHERE publication_date_epoch IS NOT NULL;
CREATE INDEX idx_author_tag_profile_tag_author ON author_tag_profile(tag_id, author_id);
CREATE INDEX idx_author_tag_profile_author_weight ON author_tag_profile(author_id, profile_weight DESC);
CREATE INDEX idx_similar_author_target ON similar_author(similar_author_id);
CREATE INDEX idx_author_refresh_unclaimed ON author_profile_refresh_queue(queued_at) WHERE claimed_at IS NULL;

SELECT setval(pg_get_serial_sequence('work_creator', 'id'),
              coalesce((SELECT max(id) FROM work_creator), 1),
              EXISTS (SELECT 1 FROM work_creator));
SELECT setval(pg_get_serial_sequence('quillent_work', 'id'),
              coalesce((SELECT max(id) FROM quillent_work), 1),
              EXISTS (SELECT 1 FROM quillent_work));
SELECT setval(pg_get_serial_sequence('work_editions', 'id'),
              coalesce((SELECT max(id) FROM work_editions), 1),
              EXISTS (SELECT 1 FROM work_editions));
SELECT setval(pg_get_serial_sequence('search_tag', 'id'),
              coalesce((SELECT max(id) FROM search_tag), 1),
              EXISTS (SELECT 1 FROM search_tag));

ANALYZE;
