-- Create Enum for the Video Processing Stage
CREATE TYPE video_stage AS ENUM ('discovered', 'downloaded', 'transcribed', 'analyzed', 'failed');

-- Table: Videos (The Raw Source)
CREATE TABLE videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_code TEXT UNIQUE NOT NULL, -- e.g. y9hwhoB9XTI
    url TEXT,
    title TEXT,
    channel TEXT,
    stage video_stage DEFAULT 'discovered',
    error_log TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create Enum for Cut Export Status
CREATE TYPE export_status AS ENUM ('pending', 'exported', 'quarantined', 'failed', 'uploaded');

-- Table: Cuts (The generated slices and AI metadata)
CREATE TABLE cuts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id UUID REFERENCES videos(id) ON DELETE CASCADE,
    cut_index INTEGER NOT NULL,
    start_time NUMERIC NOT NULL,
    end_time NUMERIC NOT NULL,
    hook_text TEXT,
    headline TEXT,
    status export_status DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(video_id, cut_index)
);

-- Table: Exports (The final rendered Shorts)
CREATE TABLE exports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cut_id UUID REFERENCES cuts(id) ON DELETE CASCADE,
    filepath TEXT NOT NULL,
    overall_score NUMERIC,
    viral_potential TEXT,
    gatekeeper_approved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Trigger to auto-update 'updated_at'
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = NOW();
   RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_videos_modtime
BEFORE UPDATE ON videos
FOR EACH ROW EXECUTE PROCEDURE update_modified_column();
