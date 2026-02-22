-- Apache AGE Graph Schema for Tower Anime Production
-- Idempotent: safe to run multiple times
-- Database: anime_production
-- Graph: anime_graph
--
-- Usage: PGPASSWORD='...' psql -h localhost -U patrick -d anime_production -f init_graph.sql

SET search_path = ag_catalog, "$user", public;

-- ============================================================
-- Vertex Labels (nodes)
-- ============================================================
-- Each DO block checks if the label already exists before creating.

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_label
    WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'anime_graph')
      AND name = 'Project'
  ) THEN
    PERFORM create_vlabel('anime_graph', 'Project');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_label
    WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'anime_graph')
      AND name = 'Character'
  ) THEN
    PERFORM create_vlabel('anime_graph', 'Character');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_label
    WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'anime_graph')
      AND name = 'Checkpoint'
  ) THEN
    PERFORM create_vlabel('anime_graph', 'Checkpoint');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_label
    WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'anime_graph')
      AND name = 'Image'
  ) THEN
    PERFORM create_vlabel('anime_graph', 'Image');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_label
    WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'anime_graph')
      AND name = 'Scene'
  ) THEN
    PERFORM create_vlabel('anime_graph', 'Scene');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_label
    WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'anime_graph')
      AND name = 'Shot'
  ) THEN
    PERFORM create_vlabel('anime_graph', 'Shot');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_label
    WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'anime_graph')
      AND name = 'Episode'
  ) THEN
    PERFORM create_vlabel('anime_graph', 'Episode');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_label
    WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'anime_graph')
      AND name = 'LoRA'
  ) THEN
    PERFORM create_vlabel('anime_graph', 'LoRA');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_label
    WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'anime_graph')
      AND name = 'FeedbackCategory'
  ) THEN
    PERFORM create_vlabel('anime_graph', 'FeedbackCategory');
  END IF;
END $$;


-- ============================================================
-- Edge Labels (relationships)
-- ============================================================

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_label
    WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'anime_graph')
      AND name = 'BELONGS_TO'
  ) THEN
    PERFORM create_elabel('anime_graph', 'BELONGS_TO');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_label
    WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'anime_graph')
      AND name = 'GENERATED_WITH'
  ) THEN
    PERFORM create_elabel('anime_graph', 'GENERATED_WITH');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_label
    WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'anime_graph')
      AND name = 'DEPICTS'
  ) THEN
    PERFORM create_elabel('anime_graph', 'DEPICTS');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_label
    WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'anime_graph')
      AND name = 'REVIEWED_AS'
  ) THEN
    PERFORM create_elabel('anime_graph', 'REVIEWED_AS');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_label
    WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'anime_graph')
      AND name = 'FEEDBACK_FOR'
  ) THEN
    PERFORM create_elabel('anime_graph', 'FEEDBACK_FOR');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_label
    WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'anime_graph')
      AND name = 'REGENERATED_FROM'
  ) THEN
    PERFORM create_elabel('anime_graph', 'REGENERATED_FROM');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_label
    WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'anime_graph')
      AND name = 'APPEARS_IN'
  ) THEN
    PERFORM create_elabel('anime_graph', 'APPEARS_IN');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_label
    WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'anime_graph')
      AND name = 'PART_OF'
  ) THEN
    PERFORM create_elabel('anime_graph', 'PART_OF');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_label
    WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'anime_graph')
      AND name = 'SCENE_IN'
  ) THEN
    PERFORM create_elabel('anime_graph', 'SCENE_IN');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_label
    WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'anime_graph')
      AND name = 'TRAINED_ON'
  ) THEN
    PERFORM create_elabel('anime_graph', 'TRAINED_ON');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_label
    WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'anime_graph')
      AND name = 'USES_LORA'
  ) THEN
    PERFORM create_elabel('anime_graph', 'USES_LORA');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_label
    WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'anime_graph')
      AND name = 'USES_CHECKPOINT'
  ) THEN
    PERFORM create_elabel('anime_graph', 'USES_CHECKPOINT');
  END IF;
END $$;
