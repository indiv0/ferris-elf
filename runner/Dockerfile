#from rust:latest
#FROM buildpack-deps:bookworm
FROM nvidia/cuda:12.3.1-base-ubuntu20.04

# Make it so that the `tzdata` doesn't need to be specified manually.
ARG DEBIAN_FRONTEND=noninteractive

# From `buildpack-deps:bookworm`
RUN set -ex; \
	apt-get update; \
	apt-get install -y --no-install-recommends \
		autoconf \
		automake \
		bzip2 \
		dpkg-dev \
		file \
		g++ \
		gcc \
		imagemagick \
		libbz2-dev \
		libc6-dev \
		libcurl4-openssl-dev \
		libdb-dev \
		libevent-dev \
		libffi-dev \
		libgdbm-dev \
		libglib2.0-dev \
		libgmp-dev \
		libjpeg-dev \
		libkrb5-dev \
		liblzma-dev \
		libmagickcore-dev \
		libmagickwand-dev \
		libmaxminddb-dev \
		libncurses5-dev \
		libncursesw5-dev \
		libpng-dev \
		libpq-dev \
		libreadline-dev \
		libsqlite3-dev \
		libssl-dev \
		libtool \
		libwebp-dev \
		libxml2-dev \
		libxslt-dev \
		libyaml-dev \
		make \
		patch \
		unzip \
		xz-utils \
		zlib1g-dev \
		\
# https://lists.debian.org/debian-devel-announce/2016/09/msg00000.html
		$( \
# if we use just "apt-cache show" here, it returns zero because "Can't select versions from package 'libmysqlclient-dev' as it is purely virtual", hence the pipe to grep
			if apt-cache show 'default-libmysqlclient-dev' 2>/dev/null | grep -q '^Version:'; then \
				echo 'default-libmysqlclient-dev'; \
			else \
				echo 'libmysqlclient-dev'; \
			fi \
		) \
	; \
	rm -rf /var/lib/apt/lists/*

# Added to make `rust:1.74.1-bookworm` work on `nvidia/cuda`.
RUN apt-get update -qq && \
  apt-get install -qq --no-install-recommends wget && \
  rm -rf /var/lib/apt/lists/*

# From `rust:1.74.1-bookworm`.
ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:$PATH \
    RUST_VERSION=1.74.1
RUN set -eux; \
    dpkgArch="$(dpkg --print-architecture)"; \
    case "${dpkgArch##*-}" in \
        amd64) rustArch='x86_64-unknown-linux-gnu'; rustupSha256='0b2f6c8f85a3d02fde2efc0ced4657869d73fccfce59defb4e8d29233116e6db' ;; \
        armhf) rustArch='armv7-unknown-linux-gnueabihf'; rustupSha256='f21c44b01678c645d8fbba1e55e4180a01ac5af2d38bcbd14aa665e0d96ed69a' ;; \
        arm64) rustArch='aarch64-unknown-linux-gnu'; rustupSha256='673e336c81c65e6b16dcdede33f4cc9ed0f08bde1dbe7a935f113605292dc800' ;; \
        i386) rustArch='i686-unknown-linux-gnu'; rustupSha256='e7b0f47557c1afcd86939b118cbcf7fb95a5d1d917bdd355157b63ca00fc4333' ;; \
        *) echo >&2 "unsupported architecture: ${dpkgArch}"; exit 1 ;; \
    esac; \
    url="https://static.rust-lang.org/rustup/archive/1.26.0/${rustArch}/rustup-init"; \
    wget "$url"; \
    echo "${rustupSha256} *rustup-init" | sha256sum -c -; \
    chmod +x rustup-init; \
    ./rustup-init -y --no-modify-path --profile minimal --default-toolchain $RUST_VERSION --default-host ${rustArch}; \
    rm rustup-init; \
    chmod -R a+w $RUSTUP_HOME $CARGO_HOME; \
    rustup --version; \
    cargo --version; \
    rustc --version;

RUN rustup install nightly
RUN rustup default nightly
ENV RUSTFLAGS="-C target-cpu=native"
ENV CARGO_TERM_COLOR="never"
ENV TERM="dumb"

# Update `vulkan`.
# See: https://stackoverflow.com/questions/74965945/vulkan-is-unable-to-detect-nvidia-gpu-from-within-a-docker-container-when-using
RUN apt-get update -qq && \
  apt-get install -y -qq --no-install-recommends \
    libxext6 \
    libvulkan1 \
    libvulkan-dev \
    vulkan-tools \
    mesa-vulkan-drivers && \
  rm -rf /var/lib/apt/lists/*
COPY nvidia_icd.json /etc/vulkan/icd.d

# These should be cached
WORKDIR /usr/src/ferris-elf
COPY build.rs build.rs
COPY Cargo.toml Cargo.toml
COPY src/main.rs src/main.rs
COPY src/placeholder.rs src/lib.rs
RUN cargo build --release
RUN cargo clean -p ferris-elf

# For each build
COPY src/code.rs src/lib.rs
RUN touch src/lib.rs
RUN timeout 60 cargo build --release

CMD ["echo ERROR"]
