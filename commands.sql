--- Add scraped video users into user_scrape
insert into user_scrape (username) (select username from video_data) on conflict do nothing;

--- Get ratio'd videos
select 'https://www.tiktok.com/@' || username || '/video/' || id as url, description, view_count, comment_count, view_count / comment_count as ratio from video_data where comment_count > 5000 and view_count > 10000 order by ratio asc limit 50;
