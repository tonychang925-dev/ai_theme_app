--
-- PostgreSQL database dump
--

\restrict IqcVsalfW1SpllqSyIp6vFeB3mW3YHNk6aNnaeENvaRFDkGJJHuz2fKT5Gvz4jX

-- Dumped from database version 14.20 (Homebrew)
-- Dumped by pg_dump version 14.20 (Homebrew)

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

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: theme_master; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.theme_master (
    id integer NOT NULL,
    name character varying(150) NOT NULL,
    code character varying(80) NOT NULL,
    description text,
    status character varying(20) DEFAULT 'active'::character varying,
    level1_category character varying(80),
    level2_category character varying(80),
    level3_category character varying(80),
    category_path text[],
    category1_code character varying(50),
    category2_code character varying(50),
    category3_code character varying(50),
    tags jsonb DEFAULT '{}'::jsonb,
    theme_type character varying(30) DEFAULT 'concept'::character varying NOT NULL,
    heat_score integer DEFAULT 50,
    confidence_score numeric(3,2) DEFAULT 0.80,
    lifecycle_stage character varying(20) DEFAULT 'growth'::character varying,
    related_stocks text[] DEFAULT '{}'::text[],
    stock_count integer DEFAULT 0,
    news_count integer DEFAULT 0,
    mention_count integer DEFAULT 0,
    last_mentioned timestamp without time zone,
    source_system character varying(50) NOT NULL,
    source_id character varying(100),
    created_by character varying(50) DEFAULT 'system'::character varying,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    last_active_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_confidence CHECK (((confidence_score >= 0.0) AND (confidence_score <= 1.0))),
    CONSTRAINT valid_lifecycle CHECK (((lifecycle_stage)::text = ANY ((ARRAY['emerging'::character varying, 'growth'::character varying, 'mature'::character varying, 'decline'::character varying, 'archived'::character varying])::text[]))),
    CONSTRAINT valid_status CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'inactive'::character varying, 'archived'::character varying])::text[]))),
    CONSTRAINT valid_theme_type CHECK (((theme_type)::text = ANY ((ARRAY['concept'::character varying, 'industry'::character varying, 'policy'::character varying, 'relation'::character varying, 'event'::character varying, 'investment'::character varying])::text[])))
);


ALTER TABLE public.theme_master OWNER TO postgres;

--
-- Name: theme_master_id_seq1; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.theme_master_id_seq1
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.theme_master_id_seq1 OWNER TO postgres;

--
-- Name: theme_master_id_seq1; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.theme_master_id_seq1 OWNED BY public.theme_master.id;


--
-- Name: theme_master id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.theme_master ALTER COLUMN id SET DEFAULT nextval('public.theme_master_id_seq1'::regclass);


--
-- Name: theme_master theme_master_code_key1; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.theme_master
    ADD CONSTRAINT theme_master_code_key1 UNIQUE (code);


--
-- Name: theme_master theme_master_pkey1; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.theme_master
    ADD CONSTRAINT theme_master_pkey1 PRIMARY KEY (id);


--
-- Name: idx_theme_active; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_theme_active ON public.theme_master USING btree (last_active_at DESC);


--
-- Name: idx_theme_cat1; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_theme_cat1 ON public.theme_master USING btree (category1_code);


--
-- Name: idx_theme_cat2; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_theme_cat2 ON public.theme_master USING btree (category2_code);


--
-- Name: idx_theme_cat3; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_theme_cat3 ON public.theme_master USING btree (category3_code);


--
-- Name: idx_theme_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_theme_created ON public.theme_master USING btree (created_at DESC);


--
-- Name: idx_theme_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_theme_status ON public.theme_master USING btree (status);


--
-- Name: idx_theme_stocks; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_theme_stocks ON public.theme_master USING gin (related_stocks);


--
-- Name: theme_master theme_master_category1_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.theme_master
    ADD CONSTRAINT theme_master_category1_code_fkey FOREIGN KEY (category1_code) REFERENCES public.financial_categories(category_code) ON DELETE SET NULL;


--
-- Name: theme_master theme_master_category2_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.theme_master
    ADD CONSTRAINT theme_master_category2_code_fkey FOREIGN KEY (category2_code) REFERENCES public.financial_categories(category_code) ON DELETE SET NULL;


--
-- Name: theme_master theme_master_category3_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.theme_master
    ADD CONSTRAINT theme_master_category3_code_fkey FOREIGN KEY (category3_code) REFERENCES public.financial_categories(category_code) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--

\unrestrict IqcVsalfW1SpllqSyIp6vFeB3mW3YHNk6aNnaeENvaRFDkGJJHuz2fKT5Gvz4jX

