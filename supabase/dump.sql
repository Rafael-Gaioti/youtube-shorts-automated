


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE EXTENSION IF NOT EXISTS "pg_graphql" WITH SCHEMA "graphql";






CREATE EXTENSION IF NOT EXISTS "pg_stat_statements" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "supabase_vault" WITH SCHEMA "vault";






CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA "extensions";






CREATE TYPE "public"."export_status" AS ENUM (
    'pending',
    'exported',
    'quarantined',
    'failed',
    'uploaded'
);


ALTER TYPE "public"."export_status" OWNER TO "postgres";


CREATE TYPE "public"."video_stage" AS ENUM (
    'discovered',
    'downloaded',
    'transcribing',
    'transcribed',
    'analyzed',
    'cutting',
    'exporting',
    'exported',
    'quarantined',
    'failed'
);


ALTER TYPE "public"."video_stage" OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_modified_column"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
   NEW.updated_at = NOW();
   RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_modified_column"() OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."cuts" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "video_id" "uuid",
    "cut_index" integer NOT NULL,
    "start_time" numeric NOT NULL,
    "end_time" numeric NOT NULL,
    "hook_text" "text",
    "headline" "text",
    "status" "public"."export_status" DEFAULT 'pending'::"public"."export_status",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "scheduled_at" timestamp with time zone,
    "youtube_views" integer DEFAULT 0,
    "youtube_likes" integer DEFAULT 0
);


ALTER TABLE "public"."cuts" OWNER TO "postgres";


COMMENT ON COLUMN "public"."cuts"."scheduled_at" IS 'Data e hora programada para publicação no YouTube';



CREATE TABLE IF NOT EXISTS "public"."exports" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "cut_id" "uuid",
    "filepath" "text" NOT NULL,
    "overall_score" numeric,
    "viral_potential" "text",
    "gatekeeper_approved" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "youtube_views" integer DEFAULT 0,
    "youtube_likes" integer DEFAULT 0
);


ALTER TABLE "public"."exports" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."managed_channels" (
    "id" "text" NOT NULL,
    "name" "text" NOT NULL,
    "youtube_handle" "text",
    "niche_persona" "text",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."managed_channels" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."system_config" (
    "id" "text" NOT NULL,
    "value" "jsonb" NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."system_config" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."videos" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "video_code" "text" NOT NULL,
    "url" "text",
    "title" "text",
    "channel" "text",
    "stage" "public"."video_stage" DEFAULT 'discovered'::"public"."video_stage",
    "error_log" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "discovery_rationale" "text",
    "niche_confidence" double precision,
    "destination_channel_id" "text"
);

ALTER TABLE ONLY "public"."videos" REPLICA IDENTITY FULL;


ALTER TABLE "public"."videos" OWNER TO "postgres";


COMMENT ON COLUMN "public"."videos"."discovery_rationale" IS 'AI explanation for why this video fits the niche';



COMMENT ON COLUMN "public"."videos"."niche_confidence" IS 'Score from 0.0 to 1.0 representing AI certainty of niche fit';



ALTER TABLE ONLY "public"."cuts"
    ADD CONSTRAINT "cuts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cuts"
    ADD CONSTRAINT "cuts_video_id_cut_index_key" UNIQUE ("video_id", "cut_index");



ALTER TABLE ONLY "public"."exports"
    ADD CONSTRAINT "exports_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."managed_channels"
    ADD CONSTRAINT "managed_channels_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."system_config"
    ADD CONSTRAINT "system_config_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."videos"
    ADD CONSTRAINT "videos_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."videos"
    ADD CONSTRAINT "videos_video_code_key" UNIQUE ("video_code");



CREATE OR REPLACE TRIGGER "update_videos_modtime" BEFORE UPDATE ON "public"."videos" FOR EACH ROW EXECUTE FUNCTION "public"."update_modified_column"();



ALTER TABLE ONLY "public"."cuts"
    ADD CONSTRAINT "cuts_video_id_fkey" FOREIGN KEY ("video_id") REFERENCES "public"."videos"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."exports"
    ADD CONSTRAINT "exports_cut_id_fkey" FOREIGN KEY ("cut_id") REFERENCES "public"."cuts"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."videos"
    ADD CONSTRAINT "videos_destination_channel_id_fkey" FOREIGN KEY ("destination_channel_id") REFERENCES "public"."managed_channels"("id");





ALTER PUBLICATION "supabase_realtime" OWNER TO "postgres";






ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."videos";



GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";

























































































































































GRANT ALL ON FUNCTION "public"."update_modified_column"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_modified_column"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_modified_column"() TO "service_role";


















GRANT ALL ON TABLE "public"."cuts" TO "anon";
GRANT ALL ON TABLE "public"."cuts" TO "authenticated";
GRANT ALL ON TABLE "public"."cuts" TO "service_role";



GRANT ALL ON TABLE "public"."exports" TO "anon";
GRANT ALL ON TABLE "public"."exports" TO "authenticated";
GRANT ALL ON TABLE "public"."exports" TO "service_role";



GRANT ALL ON TABLE "public"."managed_channels" TO "anon";
GRANT ALL ON TABLE "public"."managed_channels" TO "authenticated";
GRANT ALL ON TABLE "public"."managed_channels" TO "service_role";



GRANT ALL ON TABLE "public"."system_config" TO "anon";
GRANT ALL ON TABLE "public"."system_config" TO "authenticated";
GRANT ALL ON TABLE "public"."system_config" TO "service_role";



GRANT ALL ON TABLE "public"."videos" TO "anon";
GRANT ALL ON TABLE "public"."videos" TO "authenticated";
GRANT ALL ON TABLE "public"."videos" TO "service_role";









ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";































