--
-- PostgreSQL database dump
--

\restrict ydHphFgtA7g5d6HRVQqUhaWcv669UHjVGp5IBdQ1md0AJdITgbV8rO7PX5wu0gW

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

--
-- Data for Name: financial_categories; Type: TABLE DATA; Schema: public; Owner: postgres
--

INSERT INTO public.financial_categories VALUES (4, '240000', '有色金属', '申万一级行业[SW2021]：有色金属', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '240000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (50, '240200', '金属新材料', NULL, 2, '240000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '240200', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (51, '240300', '工业金属', NULL, 2, '240000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '240300', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (52, '240400', '贵金属', NULL, 2, '240000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '240400', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (53, '240500', '小金属', NULL, 2, '240000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '240500', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (54, '240600', '能源金属', NULL, 2, '240000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '240600', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (58, '270400', '其他电子Ⅱ', NULL, 2, '270000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '270400', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (59, '270500', '消费电子', NULL, 2, '270000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '270500', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (48, '230400', '普钢', NULL, 2, '230000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '230400', true, 3, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (49, '230500', '特钢Ⅱ', NULL, 2, '230000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '230500', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (55, '270100', '半导体', NULL, 2, '270000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '270100', true, 7, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (56, '270200', '元件', NULL, 2, '270000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '270200', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (57, '270300', '光学光电子', NULL, 2, '270000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '270300', true, 3, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (32, '110100', '种植业', NULL, 2, '110000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '110100', true, 4, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (33, '110200', '渔业', NULL, 2, '110000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '110200', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (34, '110300', '林业Ⅱ', NULL, 2, '110000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '110300', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (35, '110400', '饲料', NULL, 2, '110000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '110400', true, 3, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (36, '110500', '农产品加工', NULL, 2, '110000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '110500', true, 3, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (37, '110700', '养殖业', NULL, 2, '110000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '110700', true, 3, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (38, '110800', '动物保健Ⅱ', NULL, 2, '110000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '110800', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (39, '110900', '农业综合Ⅱ', NULL, 2, '110000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '110900', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (40, '220200', '化学原料', NULL, 2, '220000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '220200', true, 6, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (41, '220300', '化学制品', NULL, 2, '220000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '220300', true, 9, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (42, '220400', '化学纤维', NULL, 2, '220000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '220400', true, 5, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (43, '220500', '塑料', NULL, 2, '220000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '220500', true, 4, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (44, '220600', '橡胶', NULL, 2, '220000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '220600', true, 3, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (45, '220800', '农化制品', NULL, 2, '220000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '220800', true, 5, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (46, '220900', '非金属材料Ⅱ', NULL, 2, '220000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '220900', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (47, '230300', '冶钢原料', NULL, 2, '230000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '230300', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (60, '270600', '电子化学品Ⅱ', NULL, 2, '270000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '270600', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (61, '280200', '汽车零部件', NULL, 2, '280000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '280200', true, 5, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (62, '280300', '汽车服务', NULL, 2, '280000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '280300', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (63, '280400', '摩托车及其他', NULL, 2, '280000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '280400', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (64, '280500', '乘用车', NULL, 2, '280000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '280500', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (65, '280600', '商用车', NULL, 2, '280000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '280600', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (66, '330100', '白色家电', NULL, 2, '330000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '330100', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (67, '330200', '黑色家电', NULL, 2, '330000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '330200', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (68, '330300', '小家电', NULL, 2, '330000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '330300', true, 3, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (69, '330400', '厨卫电器', NULL, 2, '330000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '330400', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (70, '330500', '照明设备Ⅱ', NULL, 2, '330000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '330500', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (71, '330600', '家电零部件Ⅱ', NULL, 2, '330000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '330600', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (72, '330700', '其他家电Ⅱ', NULL, 2, '330000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '330700', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (73, '340400', '食品加工', NULL, 2, '340000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '340400', true, 4, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (74, '340500', '白酒Ⅱ', NULL, 2, '340000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '340500', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (75, '340600', '非白酒', NULL, 2, '340000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '340600', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (76, '340700', '饮料乳品', NULL, 2, '340000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '340700', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (77, '340800', '休闲食品', NULL, 2, '340000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '340800', true, 3, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (78, '340900', '调味发酵品Ⅱ', NULL, 2, '340000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '340900', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (79, '350100', '纺织制造', NULL, 2, '350000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '350100', true, 5, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (80, '350200', '服装家纺', NULL, 2, '350000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '350200', true, 4, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (81, '350300', '饰品', NULL, 2, '350000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '350300', true, 3, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (82, '360100', '造纸', NULL, 2, '360000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '360100', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (83, '360200', '包装印刷', NULL, 2, '360000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '360200', true, 5, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (84, '360300', '家居用品', NULL, 2, '360000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '360300', true, 5, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (85, '360500', '文娱用品', NULL, 2, '360000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '360500', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (86, '370100', '化学制药', NULL, 2, '370000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '370100', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (87, '370200', '中药Ⅱ', NULL, 2, '370000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '370200', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (88, '370300', '生物制品', NULL, 2, '370000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '370300', true, 3, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (89, '370400', '医药商业', NULL, 2, '370000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '370400', true, 3, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (90, '370500', '医疗器械', NULL, 2, '370000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '370500', true, 3, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (91, '370600', '医疗服务', NULL, 2, '370000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '370600', true, 4, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (92, '410100', '电力', NULL, 2, '410000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '410100', true, 8, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (93, '410300', '燃气Ⅱ', NULL, 2, '410000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '410300', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (94, '420800', '物流', NULL, 2, '420000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '420800', true, 6, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (95, '420900', '铁路公路', NULL, 2, '420000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '420900', true, 3, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (96, '421000', '航空机场', NULL, 2, '420000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '421000', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (97, '421100', '航运港口', NULL, 2, '420000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '421100', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (98, '430100', '房地产开发', NULL, 2, '430000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '430100', true, 3, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (99, '430300', '房地产服务', NULL, 2, '430000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '430300', true, 3, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (100, '450200', '贸易Ⅱ', NULL, 2, '450000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '450200', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (101, '450300', '一般零售', NULL, 2, '450000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '450300', true, 4, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (102, '450400', '专业连锁Ⅱ', NULL, 2, '450000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '450400', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (103, '450600', '互联网电商', NULL, 2, '450000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '450600', true, 3, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (104, '450700', '旅游零售Ⅱ', NULL, 2, '450000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '450700', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (105, '460600', '体育Ⅱ', NULL, 2, '460000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '460600', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (106, '460700', '本地生活服务Ⅱ', NULL, 2, '460000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '460700', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (107, '460800', '专业服务', NULL, 2, '460000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '460800', true, 4, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (108, '460900', '酒店餐饮', NULL, 2, '460000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '460900', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (109, '461000', '旅游及景区', NULL, 2, '460000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '461000', true, 4, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (110, '461100', '教育', NULL, 2, '460000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '461100', true, 3, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (111, '480200', '国有大型银行Ⅱ', NULL, 2, '480000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '480200', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (112, '480300', '股份制银行Ⅱ', NULL, 2, '480000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '480300', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (113, '480400', '城商行Ⅱ', NULL, 2, '480000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '480400', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (114, '480500', '农商行Ⅱ', NULL, 2, '480000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '480500', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (115, '480600', '其他银行Ⅱ', NULL, 2, '480000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '480600', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (116, '490100', '证券Ⅱ', NULL, 2, '490000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '490100', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (117, '490200', '保险Ⅱ', NULL, 2, '490000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '490200', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (118, '490300', '多元金融', NULL, 2, '490000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '490300', true, 7, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (119, '510100', '综合Ⅱ', NULL, 2, '510000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '510100', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (120, '610100', '水泥', NULL, 2, '610000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '610100', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (121, '610200', '玻璃玻纤', NULL, 2, '610000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '610200', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (122, '610300', '装修建材', NULL, 2, '610000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '610300', true, 5, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (123, '620100', '房屋建设Ⅱ', NULL, 2, '620000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '620100', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (124, '620200', '装修装饰Ⅱ', NULL, 2, '620000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '620200', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (125, '620300', '基础建设', NULL, 2, '620000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '620300', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (126, '620400', '专业工程', NULL, 2, '620000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '620400', true, 4, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (127, '620600', '工程咨询服务Ⅱ', NULL, 2, '620000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '620600', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (128, '630100', '电机Ⅱ', NULL, 2, '630000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '630100', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (129, '630300', '其他电源设备Ⅱ', NULL, 2, '630000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '630300', true, 3, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (130, '630500', '光伏设备', NULL, 2, '630000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '630500', true, 5, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (131, '630600', '风电设备', NULL, 2, '630000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '630600', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (132, '630700', '电池', NULL, 2, '630000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '630700', true, 5, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (133, '630800', '电网设备', NULL, 2, '630000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '630800', true, 5, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (134, '640100', '通用设备', NULL, 2, '640000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '640100', true, 6, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (135, '640200', '专用设备', NULL, 2, '640000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '640200', true, 6, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (136, '640500', '轨交设备Ⅱ', NULL, 2, '640000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '640500', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (137, '640600', '工程机械', NULL, 2, '640000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '640600', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (138, '640700', '自动化设备', NULL, 2, '640000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '640700', true, 4, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (139, '650100', '航天装备Ⅱ', NULL, 2, '650000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '650100', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (140, '650200', '航空装备Ⅱ', NULL, 2, '650000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '650200', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (141, '650300', '地面兵装Ⅱ', NULL, 2, '650000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '650300', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (142, '650400', '航海装备Ⅱ', NULL, 2, '650000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '650400', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (143, '650500', '军工电子Ⅱ', NULL, 2, '650000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '650500', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (144, '710100', '计算机设备', NULL, 2, '710000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '710100', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (145, '710300', 'IT服务Ⅱ', NULL, 2, '710000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '710300', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (146, '710400', '软件开发', NULL, 2, '710000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '710400', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (147, '720400', '游戏Ⅱ', NULL, 2, '720000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '720400', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (148, '720500', '广告营销', NULL, 2, '720000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '720500', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (149, '720600', '影视院线', NULL, 2, '720000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '720600', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (150, '720700', '数字媒体', NULL, 2, '720000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '720700', true, 6, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (151, '720800', '社交Ⅱ', NULL, 2, '720000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '720800', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (152, '720900', '出版', NULL, 2, '720000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '720900', true, 3, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (153, '721000', '电视广播Ⅱ', NULL, 2, '720000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '721000', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (154, '730100', '通信服务', NULL, 2, '730000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '730100', true, 3, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (155, '730200', '通信设备', NULL, 2, '730000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '730200', true, 4, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (156, '740100', '煤炭开采', NULL, 2, '740000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '740100', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (157, '740200', '焦炭Ⅱ', NULL, 2, '740000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '740200', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (158, '750100', '油气开采Ⅱ', NULL, 2, '750000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '750100', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (159, '750200', '油服工程', NULL, 2, '750000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '750200', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (160, '750300', '炼化及贸易', NULL, 2, '750000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '750300', true, 3, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (161, '760100', '环境治理', NULL, 2, '760000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '760100', true, 4, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (162, '760200', '环保设备Ⅱ', NULL, 2, '760000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '760200', true, 1, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (163, '770100', '个护用品', NULL, 2, '770000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '770100', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (164, '770200', '化妆品', NULL, 2, '770000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '770200', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (165, '770300', '医疗美容', NULL, 2, '770000', NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '770300', true, 2, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (1, '110000', '农林牧渔', '申万一级行业[SW2021]：农林牧渔', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '110000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (2, '220000', '基础化工', '申万一级行业[SW2021]：基础化工', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '220000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (3, '230000', '钢铁', '申万一级行业[SW2021]：钢铁', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '230000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (5, '270000', '电子', '申万一级行业[SW2021]：电子', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '270000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (6, '280000', '汽车', '申万一级行业[SW2021]：汽车', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '280000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (7, '330000', '家用电器', '申万一级行业[SW2021]：家用电器', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '330000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (8, '340000', '食品饮料', '申万一级行业[SW2021]：食品饮料', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '340000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (9, '350000', '纺织服饰', '申万一级行业[SW2021]：纺织服饰', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '350000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (10, '360000', '轻工制造', '申万一级行业[SW2021]：轻工制造', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '360000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (11, '370000', '医药生物', '申万一级行业[SW2021]：医药生物', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '370000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (12, '410000', '公用事业', '申万一级行业[SW2021]：公用事业', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '410000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (13, '420000', '交通运输', '申万一级行业[SW2021]：交通运输', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '420000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (14, '430000', '房地产', '申万一级行业[SW2021]：房地产', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '430000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (15, '450000', '商贸零售', '申万一级行业[SW2021]：商贸零售', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '450000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (16, '460000', '社会服务', '申万一级行业[SW2021]：社会服务', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '460000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (17, '480000', '银行', '申万一级行业[SW2021]：银行', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '480000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (18, '490000', '非银金融', '申万一级行业[SW2021]：非银金融', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '490000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (19, '510000', '综合', '申万一级行业[SW2021]：综合', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '510000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (20, '610000', '建筑材料', '申万一级行业[SW2021]：建筑材料', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '610000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (21, '620000', '建筑装饰', '申万一级行业[SW2021]：建筑装饰', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '620000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (22, '630000', '电力设备', '申万一级行业[SW2021]：电力设备', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '630000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (23, '640000', '机械设备', '申万一级行业[SW2021]：机械设备', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '640000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (24, '650000', '国防军工', '申万一级行业[SW2021]：国防军工', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '650000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (25, '710000', '计算机', '申万一级行业[SW2021]：计算机', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '710000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (26, '720000', '传媒', '申万一级行业[SW2021]：传媒', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '720000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (27, '730000', '通信', '申万一级行业[SW2021]：通信', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '730000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (28, '740000', '煤炭', '申万一级行业[SW2021]：煤炭', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '740000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (29, '750000', '石油石化', '申万一级行业[SW2021]：石油石化', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '750000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (30, '760000', '环保', '申万一级行业[SW2021]：环保', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '760000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');
INSERT INTO public.financial_categories VALUES (31, '770000', '美容护理', '申万一级行业[SW2021]：美容护理', 1, NULL, NULL, 'industry', 'shenwan', '{}', '{}', '{}', 'tushare', '770000', true, 0, 0, 50.00, '2026-01-26 11:28:29.121462', '2026-01-26 11:28:29.121462');


--
-- Name: financial_categories_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.financial_categories_id_seq', 497, true);


--
-- PostgreSQL database dump complete
--

\unrestrict ydHphFgtA7g5d6HRVQqUhaWcv669UHjVGp5IBdQ1md0AJdITgbV8rO7PX5wu0gW

