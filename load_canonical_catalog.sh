#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <postgres-connection> <canonical-directory>" >&2
  exit 2
fi

database_target=$1
canonical_dir=$(realpath "$2")
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

if [[ "$canonical_dir" == *"'"* || "$canonical_dir" == *$'\n'* ]]; then
  echo "Canonical directory cannot contain quotes or newlines" >&2
  exit 2
fi

required_files=(
  authors.csv author_external_identifiers.csv author_alternate_names.csv
  author_external_links.csv works.csv work_external_identifiers.csv work_covers.csv
  author_profiles.csv work_cover_urls.csv work_contributors.csv prh_work_metadata.csv
  editions.csv edition_external_identifiers.csv edition_identifiers.csv
  edition_publishers.csv edition_covers.csv edition_languages.csv
  prh_edition_metadata.csv
  work_creators.csv edition_creators.csv tags.csv work_tags.csv
  work_tag_sources.csv series.csv series_external_identifiers.csv work_series.csv
  author_tag_profiles.csv author_profile_state.csv similar_authors.csv
  work_merge_audit.csv work_merge_candidates.csv author_merge_audit.csv
  author_merge_candidates.csv validation.json
)
for filename in "${required_files[@]}"; do
  if [[ ! -f "$canonical_dir/$filename" ]]; then
    echo "Missing required file: $canonical_dir/$filename" >&2
    exit 1
  fi
done

if grep -Eq ':[[:space:]]*[1-9][0-9]*([,}]|$)' "$canonical_dir/validation.json"; then
  echo "Canonical validation contains failures; refusing to load" >&2
  cat "$canonical_dir/validation.json" >&2
  exit 1
fi

copy_csv() {
  local table=$1
  local columns=$2
  local filename=$3
  echo "Loading $table from $filename"
  psql "$database_target" -X -v ON_ERROR_STOP=1 -c \
    "\copy $table ($columns) FROM '$canonical_dir/$filename' WITH (FORMAT csv, HEADER true)"
}

echo "Creating canonical schema (the target must not contain these tables)"
psql "$database_target" -X -v ON_ERROR_STOP=1 -f "$script_dir/canonical_schema.sql"

copy_csv work_creator "id,uuid,creator_name,personal_name,birth_date,death_date,ol_id" authors.csv
copy_csv author_external_identifier "author_id,provider,external_id,is_canonical" author_external_identifiers.csv
copy_csv author_alternate_name "author_id,alternate_name,position" author_alternate_names.csv
copy_csv author_external_link "author_id,link_type,url" author_external_links.csv
copy_csv prh_author_profile "author_id,prh_author_id,biography_html,photo_url,photo_credit,photo_date,prh_url,reported_work_count,related_links" author_profiles.csv
copy_csv quillent_work "id,uuid,title,sub_title,description,first_publication_date,publication_date_epoch,isbn_ten,isbn_thirteen,language_code,num_of_pages,ol_id,cover_id,featured_covers,series,position_in_series,reading_id,prh_id,goodreads_resolved,google_resolved,featured_edition_fk" works.csv
copy_csv work_external_identifier "work_id,provider,external_id,is_canonical" work_external_identifiers.csv
copy_csv work_cover "work_id,cover_id,position" work_covers.csv
copy_csv work_cover_urls "work_id,url,provider" work_cover_urls.csv
copy_csv work_contributor "work_id,creator_id,role_code,role_description,display,primary_flag,observed_isbns,provider" work_contributors.csv
copy_csv prh_work_metadata "work_id,prh_work_id,prh_display_title,prh_url,keynote_html,positioning_html,awards,frontlistiest_isbn,isbn_counts" prh_work_metadata.csv
copy_csv work_editions "id,work_id,uuid,isbn_ten,isbn_thirteen,publication_date,publication_year,ol_id,number_of_pages,lccn,oclc_number,publisher,series,goodreads_id,google_id,asin" editions.csv
copy_csv edition_external_identifier "edition_id,provider,external_id,is_canonical" edition_external_identifiers.csv
copy_csv edition_identifier "edition_id,identifier_type,identifier,normalized_identifier,position" edition_identifiers.csv
copy_csv edition_publisher "edition_id,publisher,position" edition_publishers.csv
copy_csv edition_cover "edition_id,cover_id,position" edition_covers.csv
copy_csv edition_language "edition_id,language_code,position" edition_languages.csv
copy_csv prh_edition_metadata "edition_id,prh_work_id,isbn,trim_size,format_family,format_code,format_name,version,imprint_code,imprint_name,asin,cover_url,prh_url,series_code,series_name,series_position,custom_subject_category,sales_restriction,raw_flags" prh_edition_metadata.csv
copy_csv search_tag "id,tag_name,prevalence,weight" tags.csv
copy_csv work_creators "work_id,creator_id" work_creators.csv
copy_csv edition_creators "edition_id,creator_id" edition_creators.csv
copy_csv work_tags "work_id,tag_id" work_tags.csv
copy_csv work_tag_source "work_id,tag_id,provider,tag_source" work_tag_sources.csv
copy_csv book_series "id,uuid,prh_series_code,name,description_html,series_count,series_date,is_numbered,is_kids,prh_url" series.csv
copy_csv series_external_identifier "series_id,provider,external_id,is_canonical" series_external_identifiers.csv
copy_csv work_series "work_id,series_id,position" work_series.csv
copy_csv author_tag_profile "author_id,tag_id,work_count,catalog_share,profile_weight,updated_at" author_tag_profiles.csv
copy_csv author_profile_state "author_id,tagged_work_count,profile_hash,similarity_profile_hash,profile_generated_at,similarity_generated_at,algorithm_version" author_profile_state.csv
copy_csv similar_author "author_id,similar_author_id,similarity_score,shared_tag_count,shared_tags,rank,generated_at" similar_authors.csv
copy_csv work_merge_audit "source_work_a,source_work_b,match_rule,confidence,evidence" work_merge_audit.csv
copy_csv work_merge_candidate "source_work_a,source_work_b,match_rule,confidence,evidence" work_merge_candidates.csv
copy_csv author_merge_audit "source_author_a,source_author_b,match_rule,confidence,evidence" author_merge_audit.csv
copy_csv author_merge_candidate "normalized_name,source_author_count,sample_source_keys,match_rule,confidence,evidence" author_merge_candidates.csv

echo "Adding constraints and indexes"
psql "$database_target" -X -v ON_ERROR_STOP=1 -f "$script_dir/canonical_finalize.sql"

echo "Canonical catalog load completed"
psql "$database_target" -X -v ON_ERROR_STOP=1 -c \
  "SELECT (SELECT count(*) FROM quillent_work) AS works, (SELECT count(*) FROM work_editions) AS editions, (SELECT count(*) FROM work_creator) AS authors, (SELECT count(*) FROM search_tag) AS tags;"
