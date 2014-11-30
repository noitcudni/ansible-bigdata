CREATE TABLE active_sla (
	exec_id INT NOT NULL,
	job_name VARCHAR(128) NOT NULL,
	check_time BIGINT NOT NULL,
	rule TINYINT NOT NULL,
	enc_type TINYINT,
	options LONGBLOB NOT NULL,
	primary key(exec_id, job_name)
);
ALTER TABLE execution_logs ADD COLUMN attempt INT DEFAULT 0;
ALTER TABLE execution_logs ADD COLUMN upload_time BIGINT DEFAULT 1420099200000;
UPDATE execution_logs SET upload_time=(UNIX_TIMESTAMP()*1000) WHERE upload_time=1420099200000;

ALTER TABLE execution_logs ADD PRIMARY KEY(exec_id, name, attempt, start_byte);
ALTER TABLE execution_logs ADD INDEX ex_log_attempt (exec_id, name, attempt);
ALTER TABLE project_properties MODIFY name VARCHAR(255);


