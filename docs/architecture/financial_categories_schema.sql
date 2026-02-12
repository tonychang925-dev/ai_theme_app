--
-- PostgreSQL database dump
--

\restrict dzWpFc0mg8irO5WKkCjgXi4Xv7ZlxcUnEGxpxqMRANP4eorU8cZZqLR0vlEgeRf

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
-- Name: financial_categories; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.financial_categories (
    id integer NOT NULL,
    category_code character varying(50) NOT NULL,
    category_name character varying(100) NOT NULL,
    description text,
    category_level integer NOT NULL,
    parent_code character varying(50),
    full_path text[],
    category_type character varying(30) DEFAULT 'industry'::character varying NOT NULL,
    standard_type character varying(20),
    keywords text[] DEFAULT '{}'::text[],
    aliases text[] DEFAULT '{}'::text[],
    related_industries text[] DEFAULT '{}'::text[],
    source_system character varying(50) NOT NULL,
    source_id character varying(100),
    is_standard boolean DEFAULT true,
    theme_count integer DEFAULT 0,
    stock_count integer DEFAULT 0,
    avg_heat_score numeric(5,2) DEFAULT 50.0,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT financial_categories_category_level_check CHECK (((category_level >= 1) AND (category_level <= 3)))
);


ALTER TABLE public.financial_categories OWNER TO postgres;

--
-- Name: financial_categories_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.financial_categories_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.financial_categories_id_seq OWNER TO postgres;

--
-- Name: financial_categories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.financial_categories_id_seq OWNED BY public.financial_categories.id;


--
-- Name: financial_categories id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.financial_categories ALTER COLUMN id SET DEFAULT nextval('public.financial_categories_id_seq'::regclass);


--
-- Name: financial_categories financial_categories_category_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.financial_categories
    ADD CONSTRAINT financial_categories_category_code_key UNIQUE (category_code);


--
-- Name: financial_categories financial_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.financial_categories
    ADD CONSTRAINT financial_categories_pkey PRIMARY KEY (id);


--
-- Name: idx_categories_code; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_categories_code ON public.financial_categories USING btree (category_code);


--
-- Name: idx_categories_keywords; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_categories_keywords ON public.financial_categories USING gin (keywords);


--
-- Name: idx_categories_level; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_categories_level ON public.financial_categories USING btree (category_level);


--
-- Name: idx_categories_parent; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_categories_parent ON public.financial_categories USING btree (parent_code);


--
-- Name: idx_categories_path; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_categories_path ON public.financial_categories USING gin (full_path);


--
-- Name: idx_categories_source; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_categories_source ON public.financial_categories USING btree (source_system);


--
-- Name: idx_categories_type; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_categories_type ON public.financial_categories USING btree (category_type);


--
-- PostgreSQL database dump complete
--

\unrestrict dzWpFc0mg8irO5WKkCjgXi4Xv7ZlxcUnEGxpxqMRANP4eorU8cZZqLR0vlEgeRf

